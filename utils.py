import html
from datetime import datetime

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

esc = html.escape


def money(n):
    return f"{int(n):,}".replace(",", " ") + " so'm"


def ts(t):
    return datetime.fromtimestamp(t).strftime("%d.%m.%Y") if t else "—"


def to_int(s):
    try:
        return int((s or "").strip().replace(" ", ""))
    except ValueError:
        return None


def ikb(rows):
    """rows: [[(matn, callback_data | 'url:https://...'), ...], ...]"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, **({"url": d[4:]} if d.startswith("url:") else {"callback_data": d}))
         for t, d in row] for row in rows])


def rkb(rows):
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t) for t in r] for r in rows], resize_keyboard=True)


def grid(buttons, n):
    return [buttons[i:i + n] for i in range(0, len(buttons), n)]


async def edit(c, text, kb=None):
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await c.answer()
