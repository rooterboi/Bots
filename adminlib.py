"""Maker va sub-botlar uchun umumiy admin bo'limlari: promokod, adminlar, broadcast, /cancel."""
import asyncio
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import services as sv
from db import many
from utils import edit, ikb, money, to_int


class A(StatesGroup):
    p_code = State()
    p_amount = State()
    p_limit = State()
    p_del = State()
    add = State()
    rem = State()
    bc = State()


def back(bid):
    return "am:menu" if bid == 0 else "a:menu"


def build_router():
    r = Router()

    async def guard(c: CallbackQuery, bid, owner=False):
        ok = await (sv.is_owner(bid, c.from_user.id) if owner else sv.is_admin(bid, c.from_user.id))
        if not ok:
            await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        return ok

    @r.message(Command("cancel"), StateFilter("*"))
    async def cancel(m: Message, state: FSMContext):
        await state.clear()
        await m.answer("❌ Bekor qilindi.")

    # ---------- promokodlar ----------
    @r.callback_query(F.data == "pa:menu")
    async def pa_menu(c: CallbackQuery, bot_id: int = 0):
        if not await guard(c, bot_id):
            return
        on = await sv.gs(bot_id, "promo_enabled") == "1"
        ps = await many("SELECT * FROM promocodes WHERE scope=? ORDER BY id DESC LIMIT 20", (sv.scope(bot_id),))
        lst = "\n".join(f"<code>{p['code']}</code> — {money(p['amount'])} — {p['used']}/{p['max_uses']}" for p in ps) or "Hozircha yo'q"
        txt = f"🎟 <b>Promokodlar</b>\nHolat: {'✅ yoqilgan' if on else '🚫 o‘chirilgan'}\n\n{lst}"
        kb = ikb([[("🔴 O'chirib qo'yish" if on else "🟢 Yoqish", "pa:tog")],
                  [("➕ Yangi promokod", "pa:new"), ("🗑 Promokodni o'chirish", "pa:del")],
                  [("⬅️ Orqaga", back(bot_id))]])
        await edit(c, txt, kb)

    @r.callback_query(F.data == "pa:tog")
    async def pa_tog(c: CallbackQuery, bot_id: int = 0):
        if not await guard(c, bot_id):
            return
        await sv.toggle(bot_id, "promo_enabled")
        await pa_menu(c, bot_id)

    @r.callback_query(F.data == "pa:new")
    async def pa_new(c: CallbackQuery, state: FSMContext, bot_id: int = 0):
        if not await guard(c, bot_id):
            return
        await state.set_state(A.p_code)
        await c.message.answer("Promokod nomini yuboring (lotin harf/raqam, masalan: YANGI2026):")
        await c.answer()

    @r.message(A.p_code)
    async def p_code(m: Message, state: FSMContext):
        code = (m.text or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9_]{3,20}", code):
            return await m.answer("❌ Faqat lotin harf, raqam va _ (3-20 belgi). Qayta yuboring:")
        await state.update_data(code=code)
        await state.set_state(A.p_amount)
        await m.answer("💵 Beriladigan summa (so'm):")

    @r.message(A.p_amount)
    async def p_amount(m: Message, state: FSMContext):
        v = to_int(m.text)
        if not v or v <= 0:
            return await m.answer("❌ Musbat son yuboring:")
        await state.update_data(amount=v)
        await state.set_state(A.p_limit)
        await m.answer("👥 Necha kishi ishlata oladi (limit):")

    @r.message(A.p_limit)
    async def p_limit(m: Message, state: FSMContext, bot_id: int = 0):
        v = to_int(m.text)
        if not v or v <= 0:
            return await m.answer("❌ Musbat son yuboring:")
        d = await state.get_data()
        await state.clear()
        ok = await sv.create_promo(bot_id, d["code"], d["amount"], v)
        await m.answer(f"✅ Promokod yaratildi: <code>{d['code']}</code> — {money(d['amount'])} — limit {v}" if ok
                       else "❌ Bunday nomli promokod allaqachon bor.")

    @r.callback_query(F.data == "pa:del")
    async def pa_del(c: CallbackQuery, state: FSMContext, bot_id: int = 0):
        if not await guard(c, bot_id):
            return
        await state.set_state(A.p_del)
        await c.message.answer("O'chiriladigan promokod nomini yuboring:")
        await c.answer()

    @r.message(A.p_del)
    async def p_del(m: Message, state: FSMContext, bot_id: int = 0):
        from db import ex
        n = await ex("DELETE FROM promocodes WHERE scope=? AND code=?", (sv.scope(bot_id), (m.text or "").strip().upper()))
        await state.clear()
        await m.answer("🗑 O'chirildi." if n else "❌ Topilmadi.")

    # ---------- adminlar ----------
    @r.callback_query(F.data == "ad:menu")
    async def ad_menu(c: CallbackQuery, bot_id: int = 0):
        if not await guard(c, bot_id):
            return
        ids = await sv.admins_list(bot_id)
        txt = "👮 <b>Adminlar</b>\n\n" + ("\n".join(f"• <code>{i}</code>" for i in ids) or "Qo'shimcha adminlar yo'q")
        rows = []
        if await sv.is_owner(bot_id, c.from_user.id):
            rows.append([("➕ Admin qo'shish", "ad:add"), ("➖ Adminni ayirish", "ad:rem")])
        rows.append([("⬅️ Orqaga", back(bot_id))])
        await edit(c, txt, ikb(rows))

    @r.callback_query(F.data.in_({"ad:add", "ad:rem"}))
    async def ad_ask(c: CallbackQuery, state: FSMContext, bot_id: int = 0):
        if not await guard(c, bot_id, owner=True):
            return
        await state.set_state(A.add if c.data == "ad:add" else A.rem)
        await c.message.answer("Foydalanuvchi ID raqamini yuboring:")
        await c.answer()

    @r.message(A.add)
    async def ad_add(m: Message, state: FSMContext, bot_id: int = 0):
        if not await sv.is_owner(bot_id, m.from_user.id):
            return
        v = to_int(m.text)
        if not v:
            return await m.answer("❌ ID raqam bo'lishi kerak:")
        await sv.add_admin(bot_id, v)
        await state.clear()
        await m.answer(f"✅ <code>{v}</code> admin qilindi.")

    @r.message(A.rem)
    async def ad_rem(m: Message, state: FSMContext, bot_id: int = 0):
        if not await sv.is_owner(bot_id, m.from_user.id):
            return
        v = to_int(m.text)
        if not v:
            return await m.answer("❌ ID raqam bo'lishi kerak:")
        n = await sv.remove_admin(bot_id, v)
        await state.clear()
        await m.answer("✅ Admin olib tashlandi." if n else "❌ Bunday admin topilmadi.")

    # ---------- broadcast ----------
    @r.callback_query(F.data == "bc:start")
    async def bc_start(c: CallbackQuery, state: FSMContext, bot_id: int = 0):
        if not await guard(c, bot_id):
            return
        await state.set_state(A.bc)
        await c.message.answer("📢 Tarqatiladigan xabarni yuboring (matn, rasm, video...). Bekor qilish: /cancel")
        await c.answer()

    @r.message(A.bc)
    async def bc_send(m: Message, state: FSMContext, bot_id: int = 0):
        if not await sv.is_admin(bot_id, m.from_user.id):
            return
        await state.clear()
        ids = await sv.recipients(bot_id)
        st = await m.answer(f"⏳ Yuborilmoqda: {len(ids)} ta...")
        ok = 0
        for uid in ids:
            try:
                await m.copy_to(uid)
                ok += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await m.copy_to(uid)
                    ok += 1
                except Exception:
                    pass
            except Exception:
                pass
            await asyncio.sleep(0.05)
        await st.edit_text(f"✅ Yuborildi: {ok}/{len(ids)}")

    return r
