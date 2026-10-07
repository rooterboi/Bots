import asyncio
import os
import sqlite3
import threading

from config import DB_PATH

_conn = None
_tl = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS system_settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS bot_settings(bot_id INTEGER, key TEXT, value TEXT, PRIMARY KEY(bot_id,key));
CREATE TABLE IF NOT EXISTS maker_users(user_id INTEGER PRIMARY KEY, name TEXT, balance INTEGER DEFAULT 0, referrer INTEGER, created INTEGER);
CREATE TABLE IF NOT EXISTS maker_admins(user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS bot_instances(id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, type TEXT, token TEXT UNIQUE, username TEXT, status TEXT DEFAULT 'active', expires_at INTEGER, created INTEGER);
CREATE TABLE IF NOT EXISTS promocodes(id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT, code TEXT, amount INTEGER, max_uses INTEGER, used INTEGER DEFAULT 0, UNIQUE(scope,code));
CREATE TABLE IF NOT EXISTS promo_usage(scope TEXT, code TEXT, user_id INTEGER, PRIMARY KEY(scope,code,user_id));
CREATE TABLE IF NOT EXISTS users(bot_id INTEGER, user_id INTEGER, name TEXT, balance INTEGER DEFAULT 0, premium_until INTEGER DEFAULT 0, referrer INTEGER, quality INTEGER DEFAULT 192, joined INTEGER, PRIMARY KEY(bot_id,user_id));
CREATE TABLE IF NOT EXISTS bot_admins(bot_id INTEGER, user_id INTEGER, PRIMARY KEY(bot_id,user_id));
CREATE TABLE IF NOT EXISTS movies(bot_id INTEGER, code TEXT, title TEXT, description TEXT, file_id TEXT, file_type TEXT, tier TEXT DEFAULT 'all', poster TEXT, views INTEGER DEFAULT 0, PRIMARY KEY(bot_id,code));
CREATE TABLE IF NOT EXISTS series(bot_id INTEGER, code TEXT, title TEXT, description TEXT, tier TEXT DEFAULT 'all', poster TEXT, PRIMARY KEY(bot_id,code));
CREATE TABLE IF NOT EXISTS episodes(bot_id INTEGER, code TEXT, season INTEGER, episode INTEGER, file_id TEXT, file_type TEXT, PRIMARY KEY(bot_id,code,season,episode));
CREATE TABLE IF NOT EXISTS channels(bot_id INTEGER, chat_id INTEGER, title TEXT, link TEXT, kind TEXT, PRIMARY KEY(bot_id,chat_id,kind));
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, name TEXT, amount INTEGER, file_id TEXT, ftype TEXT, status TEXT DEFAULT 'pending', created INTEGER);
CREATE TABLE IF NOT EXISTS support_map(bot_id INTEGER, admin_id INTEGER, msg_id INTEGER, user_id INTEGER, PRIMARY KEY(bot_id,admin_id,msg_id));
CREATE TABLE IF NOT EXISTS usage(bot_id INTEGER, user_id INTEGER, day TEXT, cnt INTEGER DEFAULT 0, PRIMARY KEY(bot_id,user_id,day));
"""


def _connect():
    global _conn
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript(SCHEMA)
    _conn.commit()


def _run(sql, args, mode):
    with _tl:
        try:
            cur = _conn.execute(sql, args)
            if mode == "one":
                r = cur.fetchone()
                return dict(r) if r else None
            if mode == "all":
                return [dict(r) for r in cur.fetchall()]
            _conn.commit()
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount
        except Exception:
            _conn.rollback()
            raise


async def init():
    await asyncio.to_thread(_connect)


async def one(sql, args=()):
    return await asyncio.to_thread(_run, sql, args, "one")


async def many(sql, args=()):
    return await asyncio.to_thread(_run, sql, args, "all")


async def ex(sql, args=()):
    return await asyncio.to_thread(_run, sql, args, "exec")
