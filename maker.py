"""Asosiy Maker bot: sub-bot yaratish, balans, promokod, referal va admin panel."""
import re
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import services as sv
from config import BOT_TOKEN, OWNER_ID
from db import ex, many, one
from utils import edit, esc, ikb, money, rkb, to_int, ts

TYPE_NAME = {"kino": "🎬 Kino va Serial Bot", "music": "🎵 Musiqa va Media Bot",
             "support": "📩 Murojaat (Support) Bot", "contest": "🎁 Konkurs (Referal) Bot"}
DAYS = {"month": 30, "year": 365}
PRICE_LABELS = {
    "price_kino_month": "🎬 Kino Bot — 1 oy", "price_kino_year": "🎬 Kino Bot — 1 yil",
    "price_music_month": "🎵 Musiqa Bot — 1 oy", "price_music_year": "🎵 Musiqa Bot — 1 yil",
    "price_support_month": "📩 Murojaat Bot — 1 oy", "price_support_year": "📩 Murojaat Bot — 1 yil",
    "price_contest_month": "🎁 Konkurs Bot — 1 oy", "price_contest_year": "🎁 Konkurs Bot — 1 yil",
    "ref_bonus": "👥 Referal bonusi",
}
STATUS = {"active": "🟢 faol", "paused": "⏸ to'xtatilgan", "blocked": "🚫 bloklangan", "expired": "⌛ muddati tugagan", "invalid": "⚠️ token yaroqsiz"}


class S(StatesGroup):
    token = State()
    promo = State()
    price = State()
    bal_id = State()
    bal_amt = State()


def main_kb(admin):
    rows = [["🤖 Bot yaratish", "🗂 Botlarim"], ["💰 Balans", "➕ To'ldirish"], ["🎁 Promokod", "👥 Referal"]]
    if admin:
        rows.append(["⚙️ Admin panel"])
    return rkb(rows)


def admin_menu(owner):
    rows = []
    if owner:
        rows.append([("👮 Adminlar", "ad:menu")])
    rows += [[("💵 Narxlar", "am:prices"), ("🎟 Promokodlar", "pa:menu")],
             [("🤖 Sub-botlar", "am:bots"), ("💳 Balans (ID)", "am:bal")],
             [("💳 To'lov sozlamalari", "pay:menu"), ("📊 Statistika", "am:stats")],
             [("📢 Broadcast", "bc:start")]]
    return ikb(rows)


def build_router():
    r = Router()

    @r.message(CommandStart())
    async def start(m: Message, state: FSMContext):
        await state.clear()
        admin = await sv.is_admin(0, m.from_user.id)
        await m.answer("👋 <b>Multi-Bot Maker</b>ga xush kelibsiz!\n\nBu yerda o'z Kino va Musiqa botingizni "
                       "bir necha daqiqada yaratishingiz mumkin.", reply_markup=main_kb(admin))

    # ---------- balans / promo / referal ----------
    @r.message(StateFilter(None), F.text == "💰 Balans")
    async def bal(m: Message):
        b = await sv.get_balance(0, m.from_user.id)
        await m.answer(f"💰 Balansingiz: <b>{money(b)}</b>\n\nTo'ldirish: 💳 karta, 🎁 Promokod yoki 👥 Referal orqali.",
                       reply_markup=ikb([[("➕ Balans to'ldirish", "pay:start")]]))

    @r.message(Command("promo"))
    @r.message(StateFilter(None), F.text == "🎁 Promokod")
    async def ask_promo(m: Message, state: FSMContext):
        if await sv.gs(0, "promo_enabled") != "1":
            return await m.answer("🚫 Promokod bo'limi hozircha o'chirilgan.")
        await state.set_state(S.promo)
        await m.answer("🎁 Promokodni yuboring (bekor qilish: /cancel):")

    @r.message(S.promo)
    async def got_promo(m: Message, state: FSMContext):
        _, msg = await sv.redeem(0, m.from_user.id, m.text or "")
        await state.clear()
        await m.answer(msg)

    @r.message(StateFilter(None), F.text == "👥 Referal")
    async def ref(m: Message, bot: Bot):
        me = await bot.me()
        n = await sv.ref_count(0, m.from_user.id)
        bonus = await sv.gi(0, "ref_bonus")
        await m.answer(f"👥 <b>Referal tizimi</b>\n\nHar bir taklif qilgan do'stingiz uchun <b>{money(bonus)}</b> olasiz.\n"
                       f"Taklif qilinganlar: <b>{n}</b>\n\n🔗 Havolangiz:\nhttps://t.me/{me.username}?start=ref_{m.from_user.id}")

    # ---------- sub-bot yaratish ----------
    @r.message(StateFilter(None), F.text == "🤖 Bot yaratish")
    async def new(m: Message):
        await m.answer("Qaysi botni yaratmoqchisiz?", reply_markup=ikb([[(v, f"new:{k}")] for k, v in TYPE_NAME.items()]))

    @r.callback_query(F.data.startswith("new:"))
    async def new_type(c: CallbackQuery):
        t = c.data[4:]
        pm, py = await sv.gi(0, f"price_{t}_month"), await sv.gi(0, f"price_{t}_year")
        await edit(c, f"<b>{TYPE_NAME[t]}</b>\n\nObuna narxlari:",
                   ikb([[(f"📅 1 oy — {money(pm)}", f"per:{t}:month")], [(f"📆 1 yil — {money(py)}", f"per:{t}:year")]]))

    @r.callback_query(F.data.startswith("per:"))
    async def per(c: CallbackQuery, state: FSMContext):
        _, t, p = c.data.split(":")
        price = await sv.gi(0, f"price_{t}_{p}")
        bal = await sv.get_balance(0, c.from_user.id)
        if bal < price:
            await c.answer()
            return await c.message.answer(f"❌ Balans yetarli emas.\nKerak: {money(price)}\nSizda: {money(bal)}", reply_markup=ikb([[("➕ Balans to'ldirish", "pay:start")]]))
        await state.set_state(S.token)
        await state.update_data(t=t, p=p)
        await c.message.answer("🔑 @BotFather orqali yangi bot yarating va uning <b>tokenini</b> yuboring.\nBekor qilish: /cancel")
        await c.answer()

    @r.message(S.token, F.text)
    async def token(m: Message, state: FSMContext, manager):
        d = await state.get_data()
        tok = m.text.strip()
        try:
            await m.delete()  # token chatda qolmasin
        except Exception:
            pass
        if not re.fullmatch(r"\d{6,}:[\w-]{30,}", tok):
            return await m.answer("❌ Token formati noto'g'ri. Qayta yuboring yoki /cancel")
        if tok == BOT_TOKEN or await one("SELECT 1 FROM bot_instances WHERE token=?", (tok,)):
            return await m.answer("❌ Bu token allaqachon ulangan.")
        try:
            tb = Bot(tok)
            me = await tb.get_me()
            await tb.session.close()
        except Exception:
            return await m.answer("❌ Token yaroqsiz. Tekshirib qayta yuboring.")
        price = await sv.gi(0, f"price_{d['t']}_{d['p']}")
        if await sv.get_balance(0, m.from_user.id) < price:
            await state.clear()
            return await m.answer("❌ Balans yetarli emas.")
        await sv.add_balance(0, m.from_user.id, -price)
        exp = int(time.time()) + DAYS[d["p"]] * 86400
        iid = await ex("INSERT INTO bot_instances(owner_id,type,token,username,expires_at,created) VALUES(?,?,?,?,?,?)",
                       (m.from_user.id, d["t"], tok, me.username, exp, int(time.time())))
        await manager.start(await one("SELECT * FROM bot_instances WHERE id=?", (iid,)))
        await state.clear()
        await m.answer(f"✅ <b>{TYPE_NAME[d['t']]}</b> tayyor!\n\n🤖 @{me.username}\n📅 Amal qilish muddati: {ts(exp)}\n\n"
                       f"Botingizga kirib /admin ni bosing — shaxsiy admin panel ochiladi.")

    @r.message(StateFilter(None), F.text == "🗂 Botlarim")
    async def mine(m: Message):
        rows = await many("SELECT * FROM bot_instances WHERE owner_id=? ORDER BY id", (m.from_user.id,))
        if not rows:
            return await m.answer("Sizda hali botlar yo'q. «🤖 Bot yaratish» ni bosing.")
        for b in rows:
            kb = ikb([[("🔄 1 oyga uzaytirish", f"renew:{b['id']}")]]) if b["status"] in ("active", "expired") else None
            await m.answer(f"{TYPE_NAME[b['type']]}\n🤖 @{b['username']}\nHolat: {STATUS.get(b['status'], b['status'])}\n📅 Tugash: {ts(b['expires_at'])}", reply_markup=kb)

    @r.callback_query(F.data.startswith("renew:"))
    async def renew(c: CallbackQuery, manager):
        b = await one("SELECT * FROM bot_instances WHERE id=? AND owner_id=?", (int(c.data[6:]), c.from_user.id))
        if not b or b["status"] not in ("active", "expired"):
            return await c.answer("Uzaytirib bo'lmaydi", show_alert=True)
        price = await sv.gi(0, f"price_{b['type']}_month")
        if await sv.get_balance(0, c.from_user.id) < price:
            return await c.answer(f"Balans yetarli emas ({money(price)} kerak)", show_alert=True)
        await sv.add_balance(0, c.from_user.id, -price)
        exp = max(int(time.time()), b["expires_at"]) + 30 * 86400
        await ex("UPDATE bot_instances SET expires_at=?, status='active' WHERE id=?", (exp, b["id"]))
        await manager.start(await one("SELECT * FROM bot_instances WHERE id=?", (b["id"],)))
        await c.message.edit_text(f"✅ @{b['username']} uzaytirildi. Yangi muddat: {ts(exp)}")
        await c.answer()

    # ---------- admin panel ----------
    @r.message(Command("admin"))
    @r.message(StateFilter(None), F.text == "⚙️ Admin panel")
    async def admin(m: Message):
        if await sv.is_admin(0, m.from_user.id):
            await m.answer("⚙️ <b>Maker admin paneli</b>", reply_markup=admin_menu(m.from_user.id == OWNER_ID))

    @r.callback_query(F.data.startswith("am:"))
    async def am(c: CallbackQuery, state: FSMContext, manager):
        if not await sv.is_admin(0, c.from_user.id):
            return await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        act = c.data[3:]
        back = [("⬅️ Orqaga", "am:menu")]
        if act == "menu":
            return await edit(c, "⚙️ <b>Maker admin paneli</b>", admin_menu(c.from_user.id == OWNER_ID))

        if act == "prices":
            rows = [[(f"{lbl}: {money(await sv.gi(0, k))}", f"am:price:{k}")] for k, lbl in PRICE_LABELS.items()]
            return await edit(c, "💵 <b>Narxlar</b> (o'zgartirish uchun bosing)", ikb(rows + [back]))
        if act.startswith("price:"):
            k = act.split(":")[1]
            if k not in PRICE_LABELS:
                return await c.answer()
            await state.set_state(S.price)
            await state.update_data(key=k)
            await c.message.answer(f"{PRICE_LABELS[k]} — yangi qiymat (so'm):")
            return await c.answer()

        if act == "bots":
            bs = await many("SELECT * FROM bot_instances ORDER BY id DESC LIMIT 40")
            rows = [[(f"#{b['id']} @{b['username']} • {b['type']} • {STATUS.get(b['status'], '')[:2]}", f"am:bot:{b['id']}")] for b in bs]
            return await edit(c, f"🤖 <b>Sub-botlar</b> ({len(bs)} ta ko'rsatildi)", ikb(rows + [back]))
        if act.startswith("bot:"):
            b = await one("SELECT * FROM bot_instances WHERE id=?", (int(act.split(":")[1]),))
            if not b:
                return await c.answer("Topilmadi", show_alert=True)
            txt = (f"#{b['id']} @{b['username']}\nTuri: {b['type']}\nEga: <code>{b['owner_id']}</code>\n"
                   f"Holat: {STATUS.get(b['status'], b['status'])}\nTugash: {ts(b['expires_at'])}")
            return await edit(c, txt, ikb([[("▶️ Yoqish", f"am:st:{b['id']}:active"), ("⏸ To'xtatish", f"am:st:{b['id']}:paused")],
                                           [("🚫 Bloklash", f"am:st:{b['id']}:blocked")], [("⬅️ Ro'yxat", "am:bots")]]))
        if act.startswith("st:"):
            _, bid, st = act.split(":")
            await ex("UPDATE bot_instances SET status=? WHERE id=?", (st, int(bid)))
            if st == "active":
                await manager.start(await one("SELECT * FROM bot_instances WHERE id=?", (int(bid),)))
            else:
                await manager.stop(int(bid))
            return await c.answer(f"Holat: {st}", show_alert=True)

        if act == "bal":
            await state.set_state(S.bal_id)
            await c.message.answer("Foydalanuvchi ID sini yuboring:")
            return await c.answer()

        if act == "stats":
            u = (await one("SELECT COUNT(*) c FROM maker_users"))["c"]
            b = (await one("SELECT COUNT(*) c FROM bot_instances"))["c"]
            a = (await one("SELECT COUNT(*) c FROM bot_instances WHERE status='active'"))["c"]
            by = await many("SELECT type, COUNT(*) c FROM bot_instances GROUP BY type")
            s = (await one("SELECT COALESCE(SUM(balance),0) c FROM maker_users"))["c"]
            t = f"📊 <b>Statistika</b>\n\n👥 Foydalanuvchilar: {u}\n🤖 Sub-botlar: {b} (faol: {a})\n{' | '.join(f"{x['type']}: {x['c']}" for x in by) or '—'}\n💰 Umumiy balans: {money(s)}"
            return await edit(c, t, ikb([back]))
        await c.answer()

    @r.message(S.price)
    async def price(m: Message, state: FSMContext):
        if not await sv.is_admin(0, m.from_user.id):
            return
        v = to_int(m.text)
        if v is None or v < 0:
            return await m.answer("❌ Musbat son yuboring:")
        d = await state.get_data()
        await sv.ss(0, d["key"], v)
        await state.clear()
        await m.answer("✅ Saqlandi.")

    @r.message(S.bal_id)
    async def bal_id(m: Message, state: FSMContext):
        if not await sv.is_admin(0, m.from_user.id):
            return
        v = to_int(m.text)
        if not v or not await sv.user_exists(0, v):
            return await m.answer("❌ Bunday foydalanuvchi topilmadi. ID ni qayta yuboring:")
        await state.update_data(uid=v)
        await state.set_state(S.bal_amt)
        await m.answer(f"Joriy balans: {money(await sv.get_balance(0, v))}\nSummani yuboring (+5000 qo'shadi, -5000 ayiradi):")

    @r.message(S.bal_amt)
    async def bal_amt(m: Message, state: FSMContext, bot: Bot):
        if not await sv.is_admin(0, m.from_user.id):
            return
        v = to_int(m.text)
        if v is None:
            return await m.answer("❌ Son yuboring (masalan 5000 yoki -5000):")
        d = await state.get_data()
        nb = await sv.add_balance(0, d["uid"], v)
        await state.clear()
        await m.answer(f"✅ Yangi balans: {money(nb)}")
        try:
            await bot.send_message(d["uid"], f"💰 Balansingiz admin tomonidan o'zgartirildi: {'+' if v >= 0 else ''}{v:,} so'm\nYangi balans: {money(nb)}".replace(",", " "))
        except Exception:
            pass

    return r
