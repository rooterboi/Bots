"""Konkurs boti: do'st taklif qilish bo'yicha reyting va g'olib tanlash."""
import random

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import services as sv
from db import many
from subcommon import user_kb
from utils import esc, ikb


class CS(StatesGroup):
    text = State()


async def top(bot_id, n=10):
    return await many("SELECT u.referrer AS uid, COUNT(*) AS c, "
                      "(SELECT name FROM users x WHERE x.bot_id=u.bot_id AND x.user_id=u.referrer) AS name "
                      "FROM users u WHERE u.bot_id=? AND u.referrer IS NOT NULL GROUP BY u.referrer ORDER BY c DESC LIMIT ?", (bot_id, n))


def build_router():
    r = Router()

    @r.message(CommandStart())
    async def start(m: Message, state: FSMContext, bot: Bot, bot_id: int):
        await state.clear()
        admin = await sv.is_admin(bot_id, m.from_user.id)
        me = await bot.me()
        txt = await sv.gs(bot_id, "contest_text") or "🎁 <b>Konkurs!</b>\nDo'stlaringizni taklif qiling — eng ko'p taklif qilganlar yutadi."
        await m.answer(f"{txt}\n\n🔗 Sizning havolangiz:\nhttps://t.me/{me.username}?start=ref_{m.from_user.id}",
                       reply_markup=user_kb(admin, "contest"))

    @r.message(StateFilter(None), F.text == "🏆 Reyting")
    async def rating(m: Message, bot_id: int):
        rows = await top(bot_id)
        if not rows:
            return await m.answer("Hozircha reyting bo'sh.")
        medals = ["🥇", "🥈", "🥉"]
        await m.answer("🏆 <b>Top 10</b>\n\n" + "\n".join(f"{medals[i] if i < 3 else str(i + 1) + '.'} {esc(x['name'] or x['uid'])} — {x['c']} ta" for i, x in enumerate(rows)))

    @r.message(StateFilter(None), F.text == "📊 Ballarim")
    async def mine(m: Message, bot_id: int):
        n = await sv.ref_count(bot_id, m.from_user.id)
        await m.answer(f"📊 Siz taklif qilgan do'stlar: <b>{n}</b> ta")

    async def adm(c: CallbackQuery, bot_id):
        ok = await sv.is_admin(bot_id, c.from_user.id)
        if not ok:
            await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        return ok

    @r.callback_query(F.data == "c:text")
    async def text_ask(c: CallbackQuery, state: FSMContext, bot_id: int):
        if not await adm(c, bot_id):
            return
        await state.set_state(CS.text)
        await c.message.answer("📝 Konkurs shartlari matnini yuboring (HTML qo'llanadi). Bekor: /cancel")
        await c.answer()

    @r.message(CS.text, F.text)
    async def text_set(m: Message, state: FSMContext, bot_id: int):
        if not await sv.is_admin(bot_id, m.from_user.id):
            return
        await sv.ss(bot_id, "contest_text", m.html_text)
        await state.clear()
        await m.answer("✅ Saqlandi.")

    @r.callback_query(F.data == "c:top")
    async def a_top(c: CallbackQuery, bot_id: int):
        if not await adm(c, bot_id):
            return
        rows = await top(bot_id, 20)
        await c.message.answer("🏆 <b>Top 20</b>\n\n" + ("\n".join(f"{i + 1}. {esc(x['name'] or x['uid'])} (<code>{x['uid']}</code>) — {x['c']}" for i, x in enumerate(rows)) or "Bo'sh"))
        await c.answer()

    @r.callback_query(F.data == "c:rand")
    async def a_rand(c: CallbackQuery, bot_id: int):
        if not await adm(c, bot_id):
            return
        rows = await top(bot_id, 100000)
        if not rows:
            return await c.answer("Ishtirokchilar yo'q", show_alert=True)
        pool = [x for x in rows for _ in range(x["c"])]  # har bir taklif = 1 chipta
        w = random.choice(pool)
        await c.message.answer(f"🎲 G'olib: <b>{esc(w['name'] or w['uid'])}</b> (<code>{w['uid']}</code>) — {w['c']} ta taklif")
        await c.answer()

    return r
