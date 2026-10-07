"""Kino va Serial sub-boti."""
import random
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import services as sv
from db import ex, many, one
from subcommon import user_kb
from utils import esc, grid, ikb

TIERS = {"all": "🎬 Barchaga", "free": "🆓 Faqat Oddiy", "premium": "🔒 Faqat Premium"}


class K(StatesGroup):
    file = State()
    title = State()
    desc = State()
    poster = State()
    code = State()
    tier = State()
    ecode = State()
    season = State()
    ep = State()
    efile = State()


async def can_view(bot_id, uid, tier):
    if await sv.is_admin(bot_id, uid) or await sv.gs(bot_id, "premium_enabled") != "1":
        return True
    prem = await sv.is_premium(bot_id, uid)
    if tier == "premium":
        return prem
    if tier == "free":
        return not prem
    return True


async def deny(m, tier):
    if tier == "premium":
        await m.answer("🔒 Bu kontent faqat <b>Premium</b> foydalanuvchilar uchun.",
                       reply_markup=ikb([[("💎 Premium sotib olish", "prem:open")]]))
    else:
        await m.answer("🆓 Bu kontent faqat oddiy foydalanuvchilar uchun.")


async def send_file(bot, chat_id, fid, ftype, caption, markup=None):
    if ftype == "document":
        return await bot.send_document(chat_id, fid, caption=caption, reply_markup=markup)
    return await bot.send_video(chat_id, fid, caption=caption, reply_markup=markup)


async def season_kb(bot_id, code):
    rows = await many("SELECT DISTINCT season FROM episodes WHERE bot_id=? AND code=? ORDER BY season", (bot_id, code))
    return ikb(grid([(f"📂 {r['season']}-sezon", f"s:{code}:{r['season']}") for r in rows], 3)) if rows else None


async def free_code(bot_id):
    while True:
        c = str(random.randint(1000, 99999))
        if not await one("SELECT 1 FROM movies WHERE bot_id=? AND code=?", (bot_id, c)) and \
           not await one("SELECT 1 FROM series WHERE bot_id=? AND code=?", (bot_id, c)):
            return c


async def code_taken(bot_id, code):
    return bool(await one("SELECT 1 FROM movies WHERE bot_id=? AND code=? COLLATE NOCASE", (bot_id, code)) or
                await one("SELECT 1 FROM series WHERE bot_id=? AND code=? COLLATE NOCASE", (bot_id, code)))


async def send_code(m: Message, code, bot: Bot, bot_id):
    uid = m.from_user.id
    code = code.strip()
    mv = await one("SELECT * FROM movies WHERE bot_id=? AND code=? COLLATE NOCASE", (bot_id, code))
    if mv:
        if not await can_view(bot_id, uid, mv["tier"]):
            return await deny(m, mv["tier"])
        await ex("UPDATE movies SET views=views+1 WHERE bot_id=? AND code=?", (bot_id, mv["code"]))
        cap = f"🎬 <b>{esc(mv['title'])}</b>\n\n{esc(mv['description'] or '')}\n\n🔑 Kod: <code>{mv['code']}</code>"
        return await send_file(bot, m.chat.id, mv["file_id"], mv["file_type"], cap)
    sr = await one("SELECT * FROM series WHERE bot_id=? AND code=? COLLATE NOCASE", (bot_id, code))
    if sr:
        if not await can_view(bot_id, uid, sr["tier"]):
            return await deny(m, sr["tier"])
        kb = await season_kb(bot_id, sr["code"])
        cap = f"📺 <b>{esc(sr['title'])}</b>\n\n{esc(sr['description'] or '')}\n\n🔑 Kod: <code>{sr['code']}</code>"
        if not kb:
            return await m.answer(cap + "\n\n⏳ Qismlar hali qo'shilmagan.")
        if sr["poster"]:
            return await bot.send_photo(m.chat.id, sr["poster"], caption=cap, reply_markup=kb)
        return await m.answer(cap, reply_markup=kb)
    await m.answer("❌ Bunday kodli kino yoki serial topilmadi.")


async def autopost(bot: Bot, bot_id, kind, code, title, desc, poster):
    ch = await one("SELECT * FROM channels WHERE bot_id=? AND kind='post'", (bot_id,))
    if not ch:
        return "ℹ️ Avto-post kanal ulanmagan, kanalga joylanmadi."
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={'m' if kind == 'movie' else 's'}_{code}"
    cap = f"{'🎬' if kind == 'movie' else '📺'} <b>{esc(title)}</b>\n\n{esc(desc or '')}\n\n🔑 Kod: <code>{code}</code>"
    kb = ikb([[("▶️ Botda ko'rish", "url:" + link)]])
    try:
        if poster:
            await bot.send_photo(ch["chat_id"], poster, caption=cap, reply_markup=kb)
        else:
            await bot.send_message(ch["chat_id"], cap, reply_markup=kb)
        return "📡 Kanalga joylandi."
    except Exception as e:
        return f"⚠️ Kanalga joylab bo'lmadi: {esc(str(e))}"


def build_router():
    r = Router()

    @r.message(CommandStart())
    async def start(m: Message, command: CommandObject, state: FSMContext, bot: Bot, bot_id: int):
        await state.clear()
        a = command.args or ""
        if a[:2] in ("m_", "s_"):
            return await send_code(m, a[2:], bot, bot_id)
        admin = await sv.is_admin(bot_id, m.from_user.id)
        await m.answer("🎬 Xush kelibsiz!\n\nKino yoki serial <b>kodini</b> yuboring — men faylni jo'nataman.",
                       reply_markup=user_kb(admin))

    @r.message(Command("done"), StateFilter("*"))
    async def done(m: Message, state: FSMContext):
        await state.clear()
        await m.answer("✅ Tugatildi.")

    # ---------- foydalanuvchi: serial tugmalari ----------
    @r.callback_query(F.data.startswith("s:"))
    async def season(c: CallbackQuery, bot_id: int):
        _, code, s = c.data.split(":")
        eps = await many("SELECT episode FROM episodes WHERE bot_id=? AND code=? AND season=? ORDER BY episode", (bot_id, code, int(s)))
        rows = grid([(str(e["episode"]), f"e:{code}:{s}:{e['episode']}") for e in eps], 5)
        rows.append([("⬅️ Sezonlar", f"sb:{code}")])
        await c.message.edit_reply_markup(reply_markup=ikb(rows))
        await c.answer(f"{s}-sezon")

    @r.callback_query(F.data.startswith("sb:"))
    async def season_back(c: CallbackQuery, bot_id: int):
        kb = await season_kb(bot_id, c.data[3:])
        if kb:
            await c.message.edit_reply_markup(reply_markup=kb)
        await c.answer()

    @r.callback_query(F.data.startswith("e:"))
    async def episode(c: CallbackQuery, bot: Bot, bot_id: int):
        _, code, s, e = c.data.split(":")
        sr = await one("SELECT * FROM series WHERE bot_id=? AND code=?", (bot_id, code))
        ep = await one("SELECT * FROM episodes WHERE bot_id=? AND code=? AND season=? AND episode=?", (bot_id, code, int(s), int(e)))
        if not sr or not ep:
            return await c.answer("Topilmadi", show_alert=True)
        if not await can_view(bot_id, c.from_user.id, sr["tier"]):
            await c.answer()
            return await deny(c.message, sr["tier"])
        await send_file(bot, c.message.chat.id, ep["file_id"], ep["file_type"],
                        f"📺 <b>{esc(sr['title'])}</b>\n{s}-sezon, {e}-qism")
        await c.answer()

    # ---------- admin: kino/serial qo'shish ----------
    async def adm(c: CallbackQuery, bot_id):
        ok = await sv.is_admin(bot_id, c.from_user.id)
        if not ok:
            await c.answer("⛔ Ruxsat yo'q", show_alert=True)
        return ok

    @r.callback_query(F.data == "k:addm")
    async def addm(c: CallbackQuery, state: FSMContext, bot_id: int):
        if not await adm(c, bot_id):
            return
        await state.clear()
        await state.set_state(K.file)
        await state.update_data(kind="m")
        await c.message.answer("🎞 Kino faylini yuboring (video yoki hujjat sifatida). Bekor qilish: /cancel")
        await c.answer()

    @r.callback_query(F.data == "k:adds")
    async def adds(c: CallbackQuery, state: FSMContext, bot_id: int):
        if not await adm(c, bot_id):
            return
        await state.clear()
        await state.set_state(K.title)
        await state.update_data(kind="s")
        await c.message.answer("📺 Serial nomini yuboring:")
        await c.answer()

    @r.message(K.file, F.video | F.document)
    async def k_file(m: Message, state: FSMContext):
        if m.video:
            await state.update_data(file=m.video.file_id, ftype="video")
        else:
            await state.update_data(file=m.document.file_id, ftype="document")
        await state.set_state(K.title)
        await m.answer("📝 Nomini yuboring:")

    @r.message(K.title, F.text)
    async def k_title(m: Message, state: FSMContext):
        await state.update_data(title=m.text.strip())
        await state.set_state(K.desc)
        await m.answer("📄 Tavsifni yuboring (yo'q bo'lsa  -  ):")

    @r.message(K.desc, F.text)
    async def k_desc(m: Message, state: FSMContext):
        await state.update_data(desc="" if m.text.strip() == "-" else m.text.strip())
        await state.set_state(K.poster)
        await m.answer("🖼 Poster rasmini yuboring (yo'q bo'lsa  -  ):")

    async def ask_code(m, state):
        await state.set_state(K.code)
        await m.answer("🔑 Kod yuboring (lotin harf/raqam) yoki  -  yuborsangiz avtomatik beriladi:")

    @r.message(K.poster, F.photo)
    async def k_poster(m: Message, state: FSMContext):
        await state.update_data(poster=m.photo[-1].file_id)
        await ask_code(m, state)

    @r.message(K.poster, F.text == "-")
    async def k_poster_skip(m: Message, state: FSMContext):
        await state.update_data(poster=None)
        await ask_code(m, state)

    @r.message(K.code, F.text)
    async def k_code(m: Message, state: FSMContext, bot_id: int):
        code = m.text.strip()
        if code in ("-", "auto"):
            code = await free_code(bot_id)
        elif not re.fullmatch(r"[A-Za-z0-9_]{1,20}", code):
            return await m.answer("❌ Faqat lotin harf, raqam va _ (1-20 belgi). Qayta yuboring:")
        elif await code_taken(bot_id, code):
            return await m.answer("❌ Bu kod band. Boshqa kod yuboring:")
        await state.update_data(code=code)
        await state.set_state(K.tier)
        await m.answer("Kontent toifasini tanlang:", reply_markup=ikb([[(v, f"kt:{k}")] for k, v in TIERS.items()]))

    @r.callback_query(K.tier, F.data.startswith("kt:"))
    async def k_tier(c: CallbackQuery, state: FSMContext, bot: Bot, bot_id: int):
        tier = c.data[3:]
        d = await state.get_data()
        await state.clear()
        await c.answer()
        if d["kind"] == "m":
            await ex("INSERT OR REPLACE INTO movies(bot_id,code,title,description,file_id,file_type,tier,poster) VALUES(?,?,?,?,?,?,?,?)",
                     (bot_id, d["code"], d["title"], d["desc"], d["file"], d["ftype"], tier, d.get("poster")))
            note = await autopost(bot, bot_id, "movie", d["code"], d["title"], d["desc"], d.get("poster"))
            return await c.message.answer(f"✅ Kino saqlandi. Kod: <code>{d['code']}</code> ({TIERS[tier]})\n{note}")
        await ex("INSERT OR REPLACE INTO series(bot_id,code,title,description,tier,poster) VALUES(?,?,?,?,?,?)",
                 (bot_id, d["code"], d["title"], d["desc"], tier, d.get("poster")))
        note = await autopost(bot, bot_id, "series", d["code"], d["title"], d["desc"], d.get("poster"))
        await c.message.answer(f"✅ Serial saqlandi. Kod: <code>{d['code']}</code> ({TIERS[tier]})\n{note}",
                               reply_markup=ikb([[("➕ Qism qo'shish", f"k:ep:{d['code']}")]]))

    # ---------- admin: serial qismlari ----------
    @r.callback_query(F.data == "k:ep")
    async def ep_ask(c: CallbackQuery, state: FSMContext, bot_id: int):
        if not await adm(c, bot_id):
            return
        await state.set_state(K.ecode)
        await c.message.answer("Serial kodini yuboring:")
        await c.answer()

    @r.callback_query(F.data.startswith("k:ep:"))
    async def ep_direct(c: CallbackQuery, state: FSMContext, bot_id: int):
        if not await adm(c, bot_id):
            return
        await state.update_data(code=c.data[5:])
        await state.set_state(K.season)
        await c.message.answer("Sezon raqamini yuboring:")
        await c.answer()

    @r.message(K.ecode, F.text)
    async def ep_code(m: Message, state: FSMContext, bot_id: int):
        sr = await one("SELECT code FROM series WHERE bot_id=? AND code=? COLLATE NOCASE", (bot_id, m.text.strip()))
        if not sr:
            return await m.answer("❌ Bunday serial topilmadi. Qayta yuboring:")
        await state.update_data(code=sr["code"])
        await state.set_state(K.season)
        await m.answer("Sezon raqamini yuboring:")

    @r.message(K.season, F.text)
    async def ep_season(m: Message, state: FSMContext):
        if not m.text.strip().isdigit():
            return await m.answer("❌ Raqam yuboring:")
        await state.update_data(season=int(m.text))
        await state.set_state(K.ep)
        await m.answer("Qism raqamini yuboring:")

    @r.message(K.ep, F.text)
    async def ep_num(m: Message, state: FSMContext):
        if not m.text.strip().isdigit():
            return await m.answer("❌ Raqam yuboring (tugatish: /done):")
        await state.update_data(ep=int(m.text))
        await state.set_state(K.efile)
        await m.answer("🎞 Qism faylini yuboring:")

    @r.message(K.efile, F.video | F.document)
    async def ep_file(m: Message, state: FSMContext, bot_id: int):
        d = await state.get_data()
        fid, ft = (m.video.file_id, "video") if m.video else (m.document.file_id, "document")
        await ex("INSERT OR REPLACE INTO episodes(bot_id,code,season,episode,file_id,file_type) VALUES(?,?,?,?,?,?)",
                 (bot_id, d["code"], d["season"], d["ep"], fid, ft))
        await state.set_state(K.ep)
        await m.answer(f"✅ {d['season']}-sezon {d['ep']}-qism saqlandi.\nKeyingi qism raqamini yuboring yoki /done")

    # ---------- kod bo'yicha qidiruv (eng oxirida) ----------
    @r.message(StateFilter(None), F.text, ~F.text.startswith("/"))
    async def by_code(m: Message, bot: Bot, bot_id: int):
        await send_code(m, m.text, bot, bot_id)

    return r
