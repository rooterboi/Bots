"""Kino va Musiqa sub-botlari uchun umumiy foydalanuvchi + admin funksiyalari."""
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import services as sv
from db import ex, many, one
from utils import edit, esc, ikb, money, rkb, to_int


class C(StatesGroup):
    promo = State()
    pset = State()
    ch = State()


def user_kb(admin, btype="kino"):
    if btype == "support":
        rows = []
    elif btype == "contest":
        rows = [["👥 Referal", "🏆 Reyting"], ["📊 Ballarim"]]
    else:
        rows = [["💎 Premium", "💰 Balans"], ["➕ To'ldirish", "🎁 Promokod"], ["👥 Referal"]]
    if admin:
        rows.append(["⚙️ Admin"])
    return rkb(rows)


def menu_kb(btype):
    rows = []
    if btype == "kino":
        rows += [[("🎬 Kino qo'shish", "k:addm"), ("📺 Serial qo'shish", "k:adds")], [("➕ Serial qismi qo'shish", "k:ep")]]
    elif btype == "music":
        rows += [[("📤 Kanalga musiqa joylash", "m:post")]]
    elif btype == "contest":
        rows += [[("📝 Konkurs matni", "c:text"), ("🏆 Top 20", "c:top")], [("🎲 Tasodifiy g'olib", "c:rand")]]
    rows += [[("👮 Adminlar", "ad:menu"), ("📢 Majburiy obuna", "a:ch:sub")]]
    if btype in ("kino", "music"):
        rows += [[("📡 Avto-post kanal", "a:ch:post"), ("🎟 Promokodlar", "pa:menu")],
                 [("💎 Premium sozlamalari", "a:prem"), ("💳 To'lov sozlamalari", "pay:menu")]]
    rows += [[("📊 Statistika", "a:stats"), ("📣 Broadcast", "bc:start")]]
    return ikb(rows)


PSET_KEYS = {"premium_month": "1 oylik Premium narxi", "premium_year": "1 yillik Premium narxi",
             "ref_bonus": "Referal bonusi", "free_daily_limit": "Oddiy foydalanuvchi kunlik limiti"}


def build_router():
    r = Router()

    # ---------- foydalanuvchi ----------
    @r.message(StateFilter(None), F.text == "💰 Balans")
    async def bal(m: Message, bot_id: int):
        b = await sv.get_balance(bot_id, m.from_user.id)
        await m.answer(f"💰 Balansingiz: <b>{money(b)}</b>\n\nTo'ldirish: 💳 karta, 🎁 Promokod yoki 👥 Referal orqali.",
                       reply_markup=ikb([[("➕ Balans to'ldirish", "pay:start")]]))

    @r.message(Command("promo"))
    @r.message(StateFilter(None), F.text == "🎁 Promokod")
    async def ask_promo(m: Message, state: FSMContext, bot_id: int):
        if await sv.gs(bot_id, "promo_enabled") != "1":
            return await m.answer("🚫 Promokod bo'limi hozircha o'chirilgan.")
        await state.set_state(C.promo)
        await m.answer("🎁 Promokodni yuboring (bekor qilish: /cancel):")

    @r.message(C.promo)
    async def got_promo(m: Message, state: FSMContext, bot_id: int):
        _, msg = await sv.redeem(bot_id, m.from_user.id, m.text or "")
        await state.clear()
        await m.answer(msg)

    @r.message(StateFilter(None), F.text == "👥 Referal")
    async def ref(m: Message, bot: Bot, bot_id: int):
        me = await bot.me()
        n = await sv.ref_count(bot_id, m.from_user.id)
        bonus = await sv.gi(bot_id, "ref_bonus")
        await m.answer(f"👥 <b>Referal tizimi</b>\n\nHar bir taklif qilgan do'stingiz uchun <b>{money(bonus)}</b> olasiz.\n"
                       f"Taklif qilinganlar: <b>{n}</b>\n\n🔗 Havolangiz:\nhttps://t.me/{me.username}?start=ref_{m.from_user.id}")

    async def prem_view(uid, bot_id):
        if await sv.gs(bot_id, "premium_enabled") != "1":
            return "💎 Premium tizimi hozircha o'chirilgan.", None
        u = await one("SELECT premium_until FROM users WHERE bot_id=? AND user_id=?", (bot_id, uid))
        import time
        active = u and u["premium_until"] > time.time()
        st = f"✅ Faol (tugash: {time.strftime('%d.%m.%Y', time.localtime(u['premium_until']))})" if active else "❌ Faol emas"
        bal = await sv.get_balance(bot_id, uid)
        pm, py = await sv.gi(bot_id, "premium_month"), await sv.gi(bot_id, "premium_year")
        return (f"💎 <b>Premium</b>\nHolat: {st}\n💰 Balans: {money(bal)}",
                ikb([[(f"📅 1 oy — {money(pm)}", "prem:buy:month")], [(f"📆 1 yil — {money(py)}", "prem:buy:year")]]))

    @r.message(StateFilter(None), F.text == "💎 Premium")
    async def prem(m: Message, bot_id: int):
        t, kb = await prem_view(m.from_user.id, bot_id)
        await m.answer(t, reply_markup=kb)

    @r.callback_query(F.data == "prem:open")
    async def prem_open(c: CallbackQuery, bot_id: int):
        t, kb = await prem_view(c.from_user.id, bot_id)
        await c.message.answer(t, reply_markup=kb)
        await c.answer()

    @r.callback_query(F.data.startswith("prem:buy:"))
    async def prem_buy(c: CallbackQuery, bot_id: int):
        if await sv.gs(bot_id, "premium_enabled") != "1":
            return await c.answer("Premium tizimi o'chirilgan", show_alert=True)
        _, msg = await sv.buy_premium(bot_id, c.from_user.id, c.data.split(":")[2])
        await c.message.answer(msg)
        await c.answer()

    # ---------- admin ----------
    @r.message(Command("admin"))
    @r.message(StateFilter(None), F.text == "⚙️ Admin")
    async def admin(m: Message, btype: str, bot_id: int):
        if await sv.is_admin(bot_id, m.from_user.id):
            await m.answer("⚙️ <b>Admin panel</b>", reply_markup=menu_kb(btype))

    async def show_ch(c, kind, bot_id):
        rows_db = await many("SELECT * FROM channels WHERE bot_id=? AND kind=?", (bot_id, kind))
        title = "📢 Majburiy obuna kanallari" if kind == "sub" else "📡 Avto-post kanal"
        lst = "\n".join(f"• {esc(x['title'])}" for x in rows_db) or "Ulanmagan"
        rows = [[(f"🗑 {x['title']}", f"a:chdel:{kind}:{x['chat_id']}")] for x in rows_db]
        rows.append([("➕ Ulash" if kind == "sub" else "➕ Ulash / almashtirish", f"a:chadd:{kind}")])
        rows.append([("⬅️ Orqaga", "a:menu")])
        await edit(c, f"<b>{title}</b>\n\n{lst}\n\nBotni kanalga ADMIN qilib qo'shing.", ikb(rows))

    @r.callback_query(F.data.startswith("a:"))
    async def acb(c: CallbackQuery, state: FSMContext, btype: str, bot_id: int):
        if not await sv.is_admin(bot_id, c.from_user.id):
            return await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        act = c.data[2:]
        if act == "menu":
            return await edit(c, "⚙️ <b>Admin panel</b>", menu_kb(btype))

        if act == "stats":
            n = (await one("SELECT COUNT(*) c FROM users WHERE bot_id=?", (bot_id,)))["c"]
            import time
            p = (await one("SELECT COUNT(*) c FROM users WHERE bot_id=? AND premium_until>?", (bot_id, int(time.time()))))["c"]
            new = (await one("SELECT COUNT(*) c FROM users WHERE bot_id=? AND joined>?", (bot_id, int(time.time()) - 86400)))["c"]
            t = f"📊 <b>Statistika</b>\n\n👥 Foydalanuvchilar: {n}\n🆕 24 soatda: {new}\n💎 Premium: {p}"
            if btype == "kino":
                mv = (await one("SELECT COUNT(*) c FROM movies WHERE bot_id=?", (bot_id,)))["c"]
                sr = (await one("SELECT COUNT(*) c FROM series WHERE bot_id=?", (bot_id,)))["c"]
                t += f"\n🎬 Kinolar: {mv}\n📺 Seriallar: {sr}"
            elif btype == "music":
                from datetime import date
                d = await one("SELECT COALESCE(SUM(cnt),0) c FROM usage WHERE bot_id=? AND day=?", (bot_id, str(date.today())))
                t += f"\n⬇️ Bugungi yuklashlar: {d['c']}"
            return await edit(c, t, ikb([[("⬅️ Orqaga", "a:menu")]]))

        if act == "prem" or act == "ptog":
            if act == "ptog":
                await sv.toggle(bot_id, "premium_enabled")
            on = await sv.gs(bot_id, "premium_enabled") == "1"
            rows = [[("🔴 Premiumni o'chirish" if on else "🟢 Premiumni yoqish", "a:ptog")]]
            keys = ["premium_month", "premium_year", "ref_bonus"] + (["free_daily_limit"] if btype == "music" else [])
            for k in keys:
                v = await sv.gi(bot_id, k)
                rows.append([(f"{PSET_KEYS[k]}: {v if k == 'free_daily_limit' else money(v)}", f"a:pset:{k}")])
            rows.append([("⬅️ Orqaga", "a:menu")])
            return await edit(c, f"💎 <b>Premium sozlamalari</b>\nHolat: {'✅ yoqilgan' if on else '🚫 o‘chirilgan'}", ikb(rows))

        if act.startswith("pset:"):
            k = act.split(":")[1]
            if k not in PSET_KEYS:
                return await c.answer()
            await state.set_state(C.pset)
            await state.update_data(key=k)
            await c.message.answer(f"{PSET_KEYS[k]} — yangi qiymatni yuboring (son):")
            return await c.answer()

        if act.startswith("ch:"):
            return await show_ch(c, act[3:], bot_id)

        if act.startswith("chadd:"):
            await state.set_state(C.ch)
            await state.update_data(kind=act.split(":")[1])
            await c.message.answer("Kanal @username yoki ID sini yuboring (yoki kanaldan xabar forward qiling).\nBot kanalda admin bo'lishi shart. Bekor qilish: /cancel")
            return await c.answer()

        if act.startswith("chdel:"):
            _, kind, cid = act.split(":")
            await ex("DELETE FROM channels WHERE bot_id=? AND kind=? AND chat_id=?", (bot_id, kind, int(cid)))
            return await show_ch(c, kind, bot_id)
        await c.answer()

    @r.message(C.pset)
    async def pset(m: Message, state: FSMContext, bot_id: int):
        if not await sv.is_admin(bot_id, m.from_user.id):
            return
        v = to_int(m.text)
        if v is None or v < 0:
            return await m.answer("❌ Musbat son yuboring:")
        d = await state.get_data()
        await sv.ss(bot_id, d["key"], v)
        await state.clear()
        await m.answer("✅ Saqlandi.")

    @r.message(C.ch)
    async def ch_add(m: Message, state: FSMContext, bot: Bot, bot_id: int):
        if not await sv.is_admin(bot_id, m.from_user.id):
            return
        d = await state.get_data()
        kind = d["kind"]
        txt = (m.text or "").strip()
        fo = getattr(m, "forward_origin", None)
        if fo is not None and getattr(fo, "chat", None):
            target = fo.chat.id
        elif re.fullmatch(r"-?\d+", txt):
            target = int(txt)
        elif txt:
            target = txt if txt.startswith("@") else "@" + txt
        else:
            return await m.answer("❌ Kanal @username yoki ID yuboring.")
        try:
            chat = await bot.get_chat(target)
            me = await bot.me()
            mem = await bot.get_chat_member(chat.id, me.id)
            if mem.status not in ("administrator", "creator"):
                return await m.answer("❌ Bot kanalda admin emas. Avval botni admin qiling.")
            link = f"https://t.me/{chat.username}" if chat.username else (await bot.create_chat_invite_link(chat.id)).invite_link
        except Exception as e:
            return await m.answer(f"❌ Kanalni ulab bo'lmadi: {esc(str(e))}")
        if kind == "post":
            await ex("DELETE FROM channels WHERE bot_id=? AND kind='post'", (bot_id,))
        await ex("INSERT OR REPLACE INTO channels(bot_id,chat_id,title,link,kind) VALUES(?,?,?,?,?)",
                 (bot_id, chat.id, chat.title or str(chat.id), link, kind))
        await state.clear()
        await m.answer(f"✅ Ulandi: {esc(chat.title or '')}")

    return r
