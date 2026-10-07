"""Murojaat (Support) boti: foydalanuvchi yozadi, adminlar reply qilib javob beradi."""
from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import services as sv
from db import ex, one
from subcommon import user_kb
from utils import esc


def build_router():
    r = Router()

    @r.message(CommandStart())
    async def start(m: Message, state: FSMContext, bot_id: int):
        await state.clear()
        admin = await sv.is_admin(bot_id, m.from_user.id)
        txt = await sv.gs(bot_id, "welcome_text") or "📩 Savol yoki murojaatingizni yozing — adminlarimiz tez orada javob beradi."
        await m.answer(txt, reply_markup=user_kb(admin, "support"))

    async def is_admin_reply(m: Message, bot_id: int):
        return bool(m.reply_to_message) and await sv.is_admin(bot_id, m.from_user.id)

    async def is_user_msg(m: Message, bot_id: int):
        return not (m.text or "").startswith("/") and not await sv.is_admin(bot_id, m.from_user.id)

    # admin reply -> foydalanuvchiga
    @r.message(StateFilter(None), is_admin_reply)
    async def admin_reply(m: Message, bot: Bot, bot_id: int):
        row = await one("SELECT user_id FROM support_map WHERE bot_id=? AND admin_id=? AND msg_id=?",
                        (bot_id, m.from_user.id, m.reply_to_message.message_id))
        if not row:
            return
        try:
            await m.copy_to(row["user_id"])
            await m.answer("✅ Javob yuborildi.")
        except Exception:
            await m.answer("❌ Foydalanuvchiga yuborib bo'lmadi (botni bloklagan bo'lishi mumkin).")

    # foydalanuvchi xabari -> adminlarga
    @r.message(StateFilter(None), is_user_msg)
    async def to_admins(m: Message, bot: Bot, bot_id: int):
        sent = 0
        for a in await sv.admin_ids(bot_id):
            try:
                await bot.send_message(a, f"📩 <b>{esc(m.from_user.full_name)}</b> (<code>{m.from_user.id}</code>)"
                                          f"{' @' + m.from_user.username if m.from_user.username else ''}\n↩️ Javob berish uchun shu xabarga reply qiling.")
                cp = await m.copy_to(a)
                await ex("INSERT OR REPLACE INTO support_map(bot_id,admin_id,msg_id,user_id) VALUES(?,?,?,?)",
                         (bot_id, a, cp.message_id, m.from_user.id))
                sent += 1
            except Exception:
                pass
        await m.answer("✅ Murojaatingiz qabul qilindi." if sent else "⚠️ Hozircha adminlarga yetkazib bo'lmadi.")

    return r
