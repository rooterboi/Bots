from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

import services as sv
from utils import ikb, money


async def register_user(event, data, u):
    bid = data.get("bot_id", 0)
    ref = sv.parse_ref(event.text) if isinstance(event, Message) else None
    got = await sv.register(bid, u.id, u.full_name, ref)
    if got:
        try:
            bonus = await sv.gi(bid, "ref_bonus")
            await data["bot"].send_message(got, f"🎉 Havolangiz orqali yangi do'st qo'shildi!\n+{money(bonus)} balansingizga qo'shildi.")
        except Exception:
            pass


class Reg(BaseMiddleware):
    """Maker bot: foydalanuvchini ro'yxatga olish + referal."""

    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if u and not u.is_bot:
            await register_user(event, data, u)
        return await handler(event, data)


async def not_joined(bot, bot_id, uid):
    from db import many
    chs = await many("SELECT * FROM channels WHERE bot_id=? AND kind='sub'", (bot_id,))
    out = []
    for c in chs:
        try:
            m = await bot.get_chat_member(c["chat_id"], uid)
            if m.status in ("left", "kicked"):
                out.append(c)
        except Exception:
            pass  # bot kanalda admin emas — o'tkazib yuboramiz
    return out


class Gate(BaseMiddleware):
    """Sub-botlar: ro'yxatga olish + majburiy obuna."""

    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if not u or u.is_bot:
            return await handler(event, data)
        await register_user(event, data, u)
        bid, bot = data["bot_id"], data["bot"]
        if await sv.is_admin(bid, u.id):
            return await handler(event, data)
        chk = isinstance(event, CallbackQuery) and event.data == "chk_sub"
        missing = await not_joined(bot, bid, u.id)
        if not missing:
            if chk:
                await event.answer("✅ Rahmat!")
                try:
                    await event.message.delete()
                except Exception:
                    pass
                await event.message.answer("✅ Obuna tasdiqlandi. Endi /start ni bosing yoki havolani qayta oching.")
                return
            return await handler(event, data)
        if chk:
            return await event.answer("❌ Hali hamma kanalga obuna bo'lmadingiz", show_alert=True)
        kb = ikb([[(f"📢 {c['title']}", "url:" + c["link"])] for c in missing] + [[("✅ Tekshirish", "chk_sub")]])
        target = event.message if isinstance(event, CallbackQuery) else event
        await target.answer("🔒 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=kb)
        if isinstance(event, CallbackQuery):
            await event.answer()
