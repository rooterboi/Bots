import time
from datetime import date

from config import OWNER_ID
from db import ex, many, one

MAKER_DEF = {
    "price_kino_month": "15000", "price_kino_year": "150000",
    "price_music_month": "15000", "price_music_year": "150000",
    "price_support_month": "10000", "price_support_year": "100000",
    "price_contest_month": "10000", "price_contest_year": "100000",
    "ref_bonus": "1000", "promo_enabled": "1", "pay_enabled": "1", "min_topup": "5000",
}
SUB_DEF = {
    "premium_enabled": "0", "premium_month": "10000", "premium_year": "100000",
    "ref_bonus": "500", "promo_enabled": "1", "free_daily_limit": "5",
    "pay_enabled": "1", "min_topup": "5000",
}


def scope(bot_id):
    return "maker" if bot_id == 0 else f"b{bot_id}"


# ---------- sozlamalar ----------
async def gs(bot_id, key):
    if bot_id == 0:
        r = await one("SELECT value FROM system_settings WHERE key=?", (key,))
        d = MAKER_DEF
    else:
        r = await one("SELECT value FROM bot_settings WHERE bot_id=? AND key=?", (bot_id, key))
        d = SUB_DEF
    return r["value"] if r else d.get(key, "")


async def gi(bot_id, key):
    try:
        return int(await gs(bot_id, key))
    except ValueError:
        return 0


async def ss(bot_id, key, val):
    if bot_id == 0:
        await ex("INSERT OR REPLACE INTO system_settings(key,value) VALUES(?,?)", (key, str(val)))
    else:
        await ex("INSERT OR REPLACE INTO bot_settings(bot_id,key,value) VALUES(?,?,?)", (bot_id, key, str(val)))


async def toggle(bot_id, key):
    new = "0" if await gs(bot_id, key) == "1" else "1"
    await ss(bot_id, key, new)
    return new == "1"


# ---------- adminlik ----------
async def is_admin(bot_id, uid):
    if uid == OWNER_ID:
        return True
    if bot_id == 0:
        return bool(await one("SELECT 1 FROM maker_admins WHERE user_id=?", (uid,)))
    inst = await one("SELECT owner_id FROM bot_instances WHERE id=?", (bot_id,))
    if inst and inst["owner_id"] == uid:
        return True
    return bool(await one("SELECT 1 FROM bot_admins WHERE bot_id=? AND user_id=?", (bot_id, uid)))


async def is_owner(bot_id, uid):
    if uid == OWNER_ID:
        return True
    if bot_id == 0:
        return False
    inst = await one("SELECT owner_id FROM bot_instances WHERE id=?", (bot_id,))
    return bool(inst and inst["owner_id"] == uid)


async def admins_list(bot_id):
    if bot_id == 0:
        rows = await many("SELECT user_id FROM maker_admins")
    else:
        rows = await many("SELECT user_id FROM bot_admins WHERE bot_id=?", (bot_id,))
    return [r["user_id"] for r in rows]


async def add_admin(bot_id, uid):
    if bot_id == 0:
        await ex("INSERT OR IGNORE INTO maker_admins(user_id) VALUES(?)", (uid,))
    else:
        await ex("INSERT OR IGNORE INTO bot_admins(bot_id,user_id) VALUES(?,?)", (bot_id, uid))


async def remove_admin(bot_id, uid):
    if bot_id == 0:
        return await ex("DELETE FROM maker_admins WHERE user_id=?", (uid,))
    return await ex("DELETE FROM bot_admins WHERE bot_id=? AND user_id=?", (bot_id, uid))


# ---------- foydalanuvchi / balans ----------
def parse_ref(text):
    if text and text.startswith("/start "):
        a = text.split(maxsplit=1)[1]
        if a.startswith("ref_") and a[4:].isdigit():
            return int(a[4:])
    return None


async def register(bot_id, uid, name, ref=None):
    """Yangi foydalanuvchini yozadi. Referal bonusi berilsa, referrer ID qaytaradi."""
    now = int(time.time())
    if bot_id == 0:
        if await one("SELECT 1 FROM maker_users WHERE user_id=?", (uid,)):
            return None
        valid = bool(ref) and ref != uid and await one("SELECT 1 FROM maker_users WHERE user_id=?", (ref,))
        await ex("INSERT INTO maker_users(user_id,name,referrer,created) VALUES(?,?,?,?)",
                 (uid, name, ref if valid else None, now))
    else:
        if await one("SELECT 1 FROM users WHERE bot_id=? AND user_id=?", (bot_id, uid)):
            return None
        valid = bool(ref) and ref != uid and await one("SELECT 1 FROM users WHERE bot_id=? AND user_id=?", (bot_id, ref))
        await ex("INSERT INTO users(bot_id,user_id,name,referrer,joined) VALUES(?,?,?,?,?)",
                 (bot_id, uid, name, ref if valid else None, now))
    if valid:
        await add_balance(bot_id, ref, await gi(bot_id, "ref_bonus"))
        return ref
    return None


async def get_balance(bot_id, uid):
    if bot_id == 0:
        r = await one("SELECT balance FROM maker_users WHERE user_id=?", (uid,))
    else:
        r = await one("SELECT balance FROM users WHERE bot_id=? AND user_id=?", (bot_id, uid))
    return r["balance"] if r else 0


async def add_balance(bot_id, uid, delta):
    if bot_id == 0:
        await ex("UPDATE maker_users SET balance=MAX(0,balance+?) WHERE user_id=?", (delta, uid))
    else:
        await ex("UPDATE users SET balance=MAX(0,balance+?) WHERE bot_id=? AND user_id=?", (delta, bot_id, uid))
    return await get_balance(bot_id, uid)


async def user_exists(bot_id, uid):
    if bot_id == 0:
        return bool(await one("SELECT 1 FROM maker_users WHERE user_id=?", (uid,)))
    return bool(await one("SELECT 1 FROM users WHERE bot_id=? AND user_id=?", (bot_id, uid)))


async def ref_count(bot_id, uid):
    if bot_id == 0:
        r = await one("SELECT COUNT(*) c FROM maker_users WHERE referrer=?", (uid,))
    else:
        r = await one("SELECT COUNT(*) c FROM users WHERE bot_id=? AND referrer=?", (bot_id, uid))
    return r["c"]


async def recipients(bot_id):
    if bot_id == 0:
        rows = await many("SELECT DISTINCT owner_id AS u FROM bot_instances")
    else:
        rows = await many("SELECT user_id AS u FROM users WHERE bot_id=?", (bot_id,))
    return [r["u"] for r in rows]


# ---------- promokodlar ----------
async def create_promo(bot_id, code, amount, limit):
    try:
        await ex("INSERT INTO promocodes(scope,code,amount,max_uses) VALUES(?,?,?,?)",
                 (scope(bot_id), code.upper(), amount, limit))
        return True
    except Exception:
        return False


async def redeem(bot_id, uid, code):
    if await gs(bot_id, "promo_enabled") != "1":
        return False, "🚫 Promokod bo'limi hozircha o'chirilgan."
    sc, code = scope(bot_id), code.strip().upper()
    p = await one("SELECT * FROM promocodes WHERE scope=? AND code=?", (sc, code))
    if not p:
        return False, "❌ Bunday promokod topilmadi."
    if p["used"] >= p["max_uses"]:
        return False, "⌛ Bu promokod limiti tugagan."
    if await one("SELECT 1 FROM promo_usage WHERE scope=? AND code=? AND user_id=?", (sc, code, uid)):
        return False, "⚠️ Siz bu promokodni allaqachon ishlatgansiz."
    await ex("INSERT INTO promo_usage(scope,code,user_id) VALUES(?,?,?)", (sc, code, uid))
    await ex("UPDATE promocodes SET used=used+1 WHERE scope=? AND code=?", (sc, code))
    bal = await add_balance(bot_id, uid, p["amount"])
    return True, f"✅ Promokod qabul qilindi! +{p['amount']:,} so'm\n💰 Balans: {bal:,} so'm".replace(",", " ")


# ---------- premium ----------
async def is_premium(bot_id, uid):
    if await gs(bot_id, "premium_enabled") != "1":
        return True
    if await is_admin(bot_id, uid):
        return True
    r = await one("SELECT premium_until FROM users WHERE bot_id=? AND user_id=?", (bot_id, uid))
    return bool(r and r["premium_until"] > time.time())


async def buy_premium(bot_id, uid, period):
    price = await gi(bot_id, f"premium_{period}")
    days = 30 if period == "month" else 365
    bal = await get_balance(bot_id, uid)
    if bal < price:
        return False, f"❌ Balans yetarli emas. Kerak: {price:,} so'm, sizda: {bal:,} so'm.\n🎁 Promokod yoki 👥 Referal orqali to'ldiring.".replace(",", " ")
    await add_balance(bot_id, uid, -price)
    r = await one("SELECT premium_until FROM users WHERE bot_id=? AND user_id=?", (bot_id, uid))
    base = max(int(time.time()), r["premium_until"] if r else 0)
    until = base + days * 86400
    await ex("UPDATE users SET premium_until=? WHERE bot_id=? AND user_id=?", (until, bot_id, uid))
    return True, f"💎 Premium faollashtirildi! Tugash sanasi: {time.strftime('%d.%m.%Y', time.localtime(until))}"


async def quota_ok(bot_id, uid):
    if await is_premium(bot_id, uid):
        return True
    lim = await gi(bot_id, "free_daily_limit")
    r = await one("SELECT cnt FROM usage WHERE bot_id=? AND user_id=? AND day=?", (bot_id, uid, str(date.today())))
    return not r or r["cnt"] < lim


async def bump(bot_id, uid):
    await ex("INSERT INTO usage(bot_id,user_id,day,cnt) VALUES(?,?,?,1) "
             "ON CONFLICT(bot_id,user_id,day) DO UPDATE SET cnt=cnt+1", (bot_id, uid, str(date.today())))


async def admin_ids(bot_id):
    """To'lov/murojaat xabarlari boradigan adminlar."""
    from config import OWNER_ID
    ids = set(await admins_list(bot_id))
    if bot_id == 0:
        ids.add(OWNER_ID)
    else:
        inst = await one("SELECT owner_id FROM bot_instances WHERE id=?", (bot_id,))
        if inst:
            ids.add(inst["owner_id"])
    return [i for i in ids if i]
