"""Musiqa va Media Downloader sub-boti (yt-dlp + FFmpeg)."""
import asyncio
import glob
import html
import os
import re
import shutil
import tempfile

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message
from yt_dlp import YoutubeDL

import services as sv
from config import DOWNLOAD_DIR
from db import ex, one
from subcommon import user_kb
from utils import esc, ikb

URL_RE = re.compile(r"https?://\S+")
SEM = asyncio.Semaphore(3)
CACHE = {}  # (bot_id, chat_id, msg_id) -> {"res": [...], "page": 0}
MAXB = 50 * 1024 * 1024  # Bot API yuklash limiti


class M(StatesGroup):
    post = State()


def fmt_dur(s):
    s = int(s or 0)
    return f"{s // 60}:{s % 60:02d}"


def parse_t(x):
    parts = [int(p) for p in x.split(":")]
    t = 0
    for p in parts:
        t = t * 60 + p
    return t


# ---------- yt-dlp / ffmpeg (bloklovchi — to_thread orqali chaqiriladi) ----------
def _search(q, n=30):
    with YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}) as y:
        info = y.extract_info(f"ytsearch{n}:{q}", download=False)
    out = []
    for e in (info or {}).get("entries") or []:
        if e and e.get("id"):
            out.append({"url": f"https://www.youtube.com/watch?v={e['id']}", "title": e.get("title") or "?", "dur": e.get("duration")})
    return out


def _audio(url, outdir, kbps):
    opts = {"format": "bestaudio/best", "outtmpl": os.path.join(outdir, "%(id)s.%(ext)s"), "quiet": True,
            "no_warnings": True, "noplaylist": True,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(kbps)}]}
    with YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    if info and "entries" in info:
        info = info["entries"][0]
    return os.path.join(outdir, f"{info['id']}.mp3"), info


def _video(url, outdir):
    opts = {"format": "bv*[height<=720]+ba/b[height<=720]/b", "merge_output_format": "mp4",
            "outtmpl": os.path.join(outdir, "%(id)s.%(ext)s"), "quiet": True, "no_warnings": True, "noplaylist": True}
    with YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    if info and "entries" in info:
        info = info["entries"][0]
    files = glob.glob(os.path.join(outdir, "*"))
    return max(files, key=os.path.getsize), info


async def ffmpeg(*args):
    p = await asyncio.create_subprocess_exec("ffmpeg", "-y", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await p.communicate()
    return p.returncode == 0


def tmpdir():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    return tempfile.mkdtemp(dir=DOWNLOAD_DIR)


async def quality(bot_id, uid):
    r = await one("SELECT quality FROM users WHERE bot_id=? AND user_id=?", (bot_id, uid))
    return r["quality"] if r else 192


def page_view(res, page):
    pages = max(1, (len(res) + 9) // 10)
    chunk = res[page * 10:(page + 1) * 10]
    lines = [f"{i + 1}. {html.escape(x['title'])} — {fmt_dur(x['dur'])}" for i, x in enumerate(chunk)]
    nums = [(str(i + 1), f"ms:{page * 10 + i}") for i in range(len(chunk))]
    rows = [nums[:5], nums[5:], [("⬅️", "mp:prev"), ("❌", "mp:close"), ("➡️", "mp:next")]]
    return f"🔎 <b>Natijalar</b> ({page + 1}/{pages})\n\n" + "\n".join(lines), ikb([x for x in rows if x])


PREM_KB = ikb([[("💎 Premium sotib olish", "prem:open")]])
LIMIT_MSG = "⚠️ Bugungi bepul yuklash limitingiz tugadi. Cheksiz foydalanish uchun Premium oling."


async def send_track(bot: Bot, chat_id, url, uid, bot_id, caption=None, err_to=None):
    d = tmpdir()
    try:
        async with SEM:
            path, info = await asyncio.to_thread(_audio, url, d, await quality(bot_id, uid))
        if os.path.getsize(path) > MAXB:
            return await bot.send_message(err_to or chat_id, "❌ Fayl 50 MB dan katta, yuborib bo'lmaydi.")
        await bot.send_audio(chat_id, FSInputFile(path), title=info.get("title"), performer=info.get("uploader"),
                             duration=int(info.get("duration") or 0), caption=caption)
        await sv.bump(bot_id, uid)
    except Exception:
        await bot.send_message(err_to or chat_id, "❌ Yuklab bo'lmadi. Boshqa natijani sinab ko'ring.")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def build_router():
    r = Router()

    @r.message(CommandStart())
    async def start(m: Message, state: FSMContext, bot_id: int):
        await state.clear()
        admin = await sv.is_admin(bot_id, m.from_user.id)
        await m.answer("🎵 <b>Musiqa va Media bot</b>\n\n• Qo'shiq nomini yozing — qidiraman\n"
                       "• Instagram / TikTok / YouTube havolasini yuboring — video + MP3\n"
                       "• /quality — MP3 sifati\n• Audioga reply qilib: <code>/cut 0:10 0:40</code> — qirqish",
                       reply_markup=user_kb(admin))

    @r.message(Command("quality"))
    async def q_menu(m: Message):
        await m.answer("🎚 MP3 sifatini tanlang (kbps):", reply_markup=ikb([[(f"{q}", f"q:{q}") for q in (64, 128, 192, 320)]]))

    @r.callback_query(F.data.startswith("q:"))
    async def q_set(c: CallbackQuery, bot_id: int):
        q = int(c.data[2:])
        if q in (64, 128, 192, 320):
            await ex("UPDATE users SET quality=? WHERE bot_id=? AND user_id=?", (q, bot_id, c.from_user.id))
        await c.answer(f"✅ {q} kbps")
        await c.message.edit_text(f"🎚 MP3 sifati: <b>{q} kbps</b>")

    @r.message(Command("cut"))
    async def cut(m: Message, command: CommandObject, bot: Bot, bot_id: int):
        src = m.reply_to_message
        media = src and (src.audio or src.voice or src.document)
        args = (command.args or "").split()
        if not media or len(args) != 2:
            return await m.answer("✂️ Audio xabarga reply qilib yozing:\n<code>/cut 0:10 0:40</code>")
        try:
            s, e = parse_t(args[0]), parse_t(args[1])
            assert e > s
        except Exception:
            return await m.answer("❌ Vaqt noto'g'ri. Misol: <code>/cut 10 40</code> yoki <code>/cut 0:10 1:05</code>")
        d = tmpdir()
        try:
            a = os.path.join(d, "in")
            await bot.download(media, destination=a)
            out = os.path.join(d, "cut.mp3")
            ok = await ffmpeg("-i", a, "-ss", str(s), "-to", str(e), "-c:a", "libmp3lame", "-b:a", f"{await quality(bot_id, m.from_user.id)}k", out)
            if not ok:
                return await m.answer("❌ Qirqib bo'lmadi.")
            await m.answer_audio(FSInputFile(out), title="Qirqilgan audio")
        except Exception:
            await m.answer("❌ Faylni yuklab bo'lmadi (Telegram limiti: 20 MB).")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # ---------- havola: video + MP3 ----------
    @r.message(StateFilter(None), lambda m: bool(m.text and URL_RE.search(m.text)))
    async def link(m: Message, bot: Bot, bot_id: int):
        uid = m.from_user.id
        if not await sv.quota_ok(bot_id, uid):
            return await m.answer(LIMIT_MSG, reply_markup=PREM_KB)
        url = URL_RE.search(m.text).group(0)
        st = await m.answer("⏳ Yuklanmoqda...")
        d = tmpdir()
        try:
            async with SEM:
                path, info = await asyncio.to_thread(_video, url, d)
            title = esc(info.get("title") or "")[:200]
            if os.path.getsize(path) <= MAXB:
                await m.answer_video(FSInputFile(path), caption=f"🎬 {title}")
            else:
                await m.answer("⚠️ Video 50 MB dan katta — faqat audio yuboriladi.")
            mp3 = os.path.join(d, "audio.mp3")
            if await ffmpeg("-i", path, "-vn", "-b:a", f"{await quality(bot_id, uid)}k", mp3) and os.path.getsize(mp3) <= MAXB:
                await m.answer_audio(FSInputFile(mp3), title=info.get("title"), performer=info.get("uploader"))
            await sv.bump(bot_id, uid)
        except Exception:
            await m.answer("❌ Havoladan yuklab bo'lmadi (yopiq/noto'g'ri havola yoki platforma cheklovi).")
        finally:
            shutil.rmtree(d, ignore_errors=True)
            try:
                await st.delete()
            except Exception:
                pass

    # ---------- matn bo'yicha qidiruv ----------
    @r.message(StateFilter(None), F.text, ~F.text.startswith("/"))
    async def search(m: Message, bot_id: int):
        st = await m.answer("🔎 Qidirilmoqda...")
        try:
            res = await asyncio.to_thread(_search, m.text.strip())
        except Exception:
            res = []
        if not res:
            return await st.edit_text("❌ Hech narsa topilmadi.")
        if len(CACHE) > 500:
            for k in list(CACHE)[:100]:
                CACHE.pop(k, None)
        CACHE[(bot_id, st.chat.id, st.message_id)] = {"res": res, "page": 0}
        t, kb = page_view(res, 0)
        await st.edit_text(t, reply_markup=kb)

    @r.callback_query(F.data.startswith("mp:"))
    async def nav(c: CallbackQuery, bot_id: int):
        key = (bot_id, c.message.chat.id, c.message.message_id)
        act = c.data[3:]
        if act == "close":
            CACHE.pop(key, None)
            await c.message.delete()
            return await c.answer()
        st = CACHE.get(key)
        if not st:
            return await c.answer("Qidiruv eskirgan, qayta qidiring", show_alert=True)
        pages = max(1, (len(st["res"]) + 9) // 10)
        new = st["page"] + (1 if act == "next" else -1)
        if not 0 <= new < pages:
            return await c.answer("Bu chekka sahifa")
        st["page"] = new
        t, kb = page_view(st["res"], new)
        await c.message.edit_text(t, reply_markup=kb)
        await c.answer()

    @r.callback_query(F.data.startswith("ms:"))
    async def pick(c: CallbackQuery, bot: Bot, bot_id: int):
        st = CACHE.get((bot_id, c.message.chat.id, c.message.message_id))
        if not st:
            return await c.answer("Qidiruv eskirgan, qayta qidiring", show_alert=True)
        if not await sv.quota_ok(bot_id, c.from_user.id):
            await c.answer()
            return await c.message.answer(LIMIT_MSG, reply_markup=PREM_KB)
        item = st["res"][int(c.data[3:])]
        await c.answer("⏳ Yuklanmoqda...")
        await send_track(bot, c.message.chat.id, item["url"], c.from_user.id, bot_id)

    # ---------- admin: kanalga musiqa joylash ----------
    @r.callback_query(F.data == "m:post")
    async def post_ask(c: CallbackQuery, state: FSMContext, bot_id: int):
        if not await sv.is_admin(bot_id, c.from_user.id):
            return await c.answer("⛔", show_alert=True)
        await state.set_state(M.post)
        await c.message.answer("🎵 Kanalga joylanadigan qo'shiq nomini yuboring (bekor: /cancel):")
        await c.answer()

    @r.message(M.post, F.text)
    async def post_do(m: Message, state: FSMContext, bot: Bot, bot_id: int):
        await state.clear()
        ch = await one("SELECT * FROM channels WHERE bot_id=? AND kind='post'", (bot_id,))
        if not ch:
            return await m.answer("ℹ️ Avval Avto-post kanalni ulang.")
        st = await m.answer("⏳ Qidirilmoqda va yuklanmoqda...")
        res = await asyncio.to_thread(_search, m.text.strip(), 1)
        if not res:
            return await st.edit_text("❌ Topilmadi.")
        me = await bot.me()
        await send_track(bot, ch["chat_id"], res[0]["url"], m.from_user.id, bot_id, caption=f"🎧 Ko'proq musiqa: @{me.username}", err_to=m.chat.id)
        await st.edit_text("📡 Kanalga joylandi.")

    return r
