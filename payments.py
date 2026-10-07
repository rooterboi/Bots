"""Plastik karta orqali balans to'ldirish (qo'lda tasdiqlash). Maker va barcha sub-botlar uchun."""
import re
import time

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import services as sv
from db import ex, many, one
from utils import edit, esc, ikb, money, to_int

SETTINGS = {"card_number": "💳 Karta raqami", "card_holder": "👤 Karta egasi", "min_topup": "💵 Minimal summa"}


class P(StatesGroup):
    amount = State()
    receipt = State()
    val = State()


def fmt_card(n):
    n = re.sub(r"\D", "", n or "")
    return " ".join(n[i:i + 4] for i in range(0, len(n), 4))


async def push(bot: Bot, chat_id, p):
    cap = f"💳 <b>To'lov #{p['id']}</b>\n👤 {esc(p['name'] or '')} (<code>{p['user_id']}</code>)\n💵 {money(p['amount'])}"
    kb = ikb([[("✅ Tasdiqlash", f"pay:ok:{p['id']}"), ("❌ Rad etish", f"pay:no:{p['id']}")]])
    if p["ftype"] == "photo":
        await bot.send_photo(chat_id, p["file_id"], caption=cap, reply_markup=kb)
    else:
        await bot.send_document(chat_id, p["file_id"], caption=cap, reply_markup=kb)


def build_router():
    r = Router()

    async def start_pay(msg: Message, state: FSMContext, bid):
        card = await sv.gs(bid, "card_number")
        if await sv.gs(bid, "pay_enabled") != "1" or not card:
            return await msg.answer("💳 Karta orqali to'lov hozircha mavjud emas. Balansni 🎁 Promokod yoki 👥 Referal orqali to'ldiring.")
        await state.set_state(P.amount)
        await msg.answer(f"💳 <b>Balansni to'ldirish</b>\n\nQancha to'ldirmoqchisiz? Summani yuboring (kamida {money(await sv.gi(bid, 'min_topup'))}).\nBekor qilish: /cancel")

    @r.message(StateFilter(None), F.text == "➕ To'ldirish")
    async def pay_btn(m: Message, state: FSMContext, bot_id: int = 0):
        await start_pay(m, state, bot_id)

    @r.callback_query(F.data == "pay:start")
    async def pay_cb(c: CallbackQuery, state: FSMContext, bot_id: int = 0):
        await c.answer()
        await start_pay(c.message, state, bot_id)

    @r.message(P.amount)
    async def amount(m: Message, state: FSMContext, bot_id: int = 0):
        v, mn = to_int(m.text), await sv.gi(bot_id, "min_topup")
        if v is None or v < mn:
            return await m.answer(f"❌ Kamida {money(mn)} yuboring:")
        await state.update_data(amount=v)
        await state.set_state(P.receipt)
        await m.answer(f"💳 Karta: <code>{fmt_card(await sv.gs(bot_id, 'card_number'))}</code>\n"
                       f"👤 Egasi: <b>{esc(await sv.gs(bot_id, 'card_holder'))}</b>\n💵 Summa: <b>{money(v)}</b>\n\n"
                       "Shu kartaga pul o'tkazing va <b>chek (skrinshot)</b> rasmini yuboring.")

    @r.message(P.receipt, F.photo | F.document)
    async def receipt(m: Message, state: FSMContext, bot: Bot, bot_id: int = 0):
        d = await state.get_data()
        fid, ft = (m.photo[-1].file_id, "photo") if m.photo else (m.document.file_id, "document")
        pid = await ex("INSERT INTO payments(bot_id,user_id,name,amount,file_id,ftype,created) VALUES(?,?,?,?,?,?,?)",
                       (bot_id, m.from_user.id, m.from_user.full_name, d["amount"], fid, ft, int(time.time())))
        await state.clear()
        p = await one("SELECT * FROM payments WHERE id=?", (pid,))
        for a in await sv.admin_ids(bot_id):
            try:
                await push(bot, a, p)
            except Exception:
                pass
        await m.answer("✅ So'rov adminga yuborildi. Tasdiqlangach balansingiz to'ldiriladi.")

    @r.message(P.receipt)
    async def receipt_remind(m: Message):
        await m.answer("🧾 Iltimos, to'lov chekining rasmini yuboring (yoki /cancel).")

    @r.callback_query(F.data.startswith("pay:ok:") | F.data.startswith("pay:no:"))
    async def decide(c: CallbackQuery, bot: Bot, bot_id: int = 0):
        if not await sv.is_admin(bot_id, c.from_user.id):
            return await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        _, act, pid = c.data.split(":")
        p = await one("SELECT * FROM payments WHERE id=? AND bot_id=?", (int(pid), bot_id))
        if not p:
            return await c.answer("Topilmadi", show_alert=True)
        ok = act == "ok"
        n = await ex("UPDATE payments SET status=? WHERE id=? AND status='pending'", ("approved" if ok else "rejected", p["id"]))
        if not n:
            return await c.answer("Bu to'lov allaqachon ko'rib chiqilgan", show_alert=True)
        if ok:
            nb = await sv.add_balance(bot_id, p["user_id"], p["amount"])
            msg = f"✅ To'lovingiz tasdiqlandi! +{money(p['amount'])}\n💰 Balans: {money(nb)}"
        else:
            msg = "❌ To'lovingiz rad etildi. Savol bo'lsa admin bilan bog'laning."
        try:
            await bot.send_message(p["user_id"], msg)
        except Exception:
            pass
        try:
            await c.message.edit_caption(caption=f"{c.message.caption or ''}\n\n{'✅ Tasdiqlandi' if ok else '❌ Rad etildi'} ({esc(c.from_user.full_name)})")
        except Exception:
            pass
        await c.answer("Bajarildi")

    # ---------- admin: to'lov sozlamalari ----------
    @r.callback_query(F.data.in_({"pay:menu", "pay:tog"}))
    async def menu(c: CallbackQuery, bot_id: int = 0):
        if not await sv.is_admin(bot_id, c.from_user.id):
            return await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        if c.data == "pay:tog":
            await sv.toggle(bot_id, "pay_enabled")
        on = await sv.gs(bot_id, "pay_enabled") == "1"
        card, holder = await sv.gs(bot_id, "card_number"), await sv.gs(bot_id, "card_holder")
        pend = (await one("SELECT COUNT(*) c FROM payments WHERE bot_id=? AND status='pending'", (bot_id,)))["c"]
        txt = (f"💳 <b>To'lov sozlamalari</b>\nHolat: {'✅ yoqilgan' if on else '🚫 o‘chirilgan'}\n\n"
               f"Karta: <code>{fmt_card(card) or '—'}</code>\nEgasi: {esc(holder) or '—'}\n"
               f"Minimal summa: {money(await sv.gi(bot_id, 'min_topup'))}\nKutilayotgan to'lovlar: {pend}")
        rows = [[("🔴 O'chirish" if on else "🟢 Yoqish", "pay:tog")]]
        rows += [[(lbl, f"pay:set:{k}")] for k, lbl in SETTINGS.items()]
        rows += [[("🧾 Kutilayotgan to'lovlar", "pay:list")], [("⬅️ Orqaga", "am:menu" if bot_id == 0 else "a:menu")]]
        await edit(c, txt, ikb(rows))

    @r.callback_query(F.data.startswith("pay:set:"))
    async def set_ask(c: CallbackQuery, state: FSMContext, bot_id: int = 0):
        if not await sv.is_admin(bot_id, c.from_user.id):
            return await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        k = c.data.split(":")[2]
        if k not in SETTINGS:
            return await c.answer()
        await state.set_state(P.val)
        await state.update_data(key=k)
        hint = {"card_number": "16 xonali karta raqamini yuboring:", "card_holder": "Karta egasining ismini yuboring:",
                "min_topup": "Minimal summani yuboring (so'm):"}[k]
        await c.message.answer(hint)
        await c.answer()

    @r.message(P.val, F.text)
    async def set_val(m: Message, state: FSMContext, bot_id: int = 0):
        if not await sv.is_admin(bot_id, m.from_user.id):
            return
        k = (await state.get_data())["key"]
        t = m.text.strip()
        if k == "card_number":
            t = re.sub(r"\D", "", t)
            if len(t) not in (16, 19):
                return await m.answer("❌ Karta raqami 16 ta raqamdan iborat bo'lishi kerak. Qayta yuboring:")
        elif k == "min_topup":
            t = to_int(t)
            if t is None or t < 0:
                return await m.answer("❌ Musbat son yuboring:")
        await sv.ss(bot_id, k, t)
        await state.clear()
        await m.answer("✅ Saqlandi. /admin → 💳 To'lov sozlamalari")

    @r.callback_query(F.data == "pay:list")
    async def plist(c: CallbackQuery, bot: Bot, bot_id: int = 0):
        if not await sv.is_admin(bot_id, c.from_user.id):
            return await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        ps = await many("SELECT * FROM payments WHERE bot_id=? AND status='pending' ORDER BY id LIMIT 10", (bot_id,))
        if not ps:
            return await c.answer("Kutilayotgan to'lov yo'q", show_alert=True)
        for p in ps:
            await push(bot, c.message.chat.id, p)
        await c.answer()

    return r
