import asyncio
import logging
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

import adminlib
import db
import maker
import payments
from config import BOT_TOKEN, OWNER_ID, PORT
from db import ex, many
from manager import Manager
from middleware import Reg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def health_server():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()


async def expiry_loop(manager: Manager, bot: Bot):
    while True:
        await asyncio.sleep(600)
        try:
            for b in await many("SELECT * FROM bot_instances WHERE status='active' AND expires_at<?", (int(time.time()),)):
                await ex("UPDATE bot_instances SET status='expired' WHERE id=?", (b["id"],))
                await manager.stop(b["id"])
                try:
                    await bot.send_message(b["owner_id"], f"⌛ @{b['username']} muddati tugadi va to'xtatildi.\nUzaytirish: «🗂 Botlarim».")
                except Exception:
                    pass
        except Exception:
            logging.exception("expiry_loop")


async def main():
    if not BOT_TOKEN or not OWNER_ID:
        raise SystemExit("MAKER_BOT_TOKEN va OWNER_ID muhit o'zgaruvchilarini kiriting (.env.example ga qarang).")
    await db.init()
    manager = Manager()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage(), manager=manager)
    reg = Reg()
    dp.message.outer_middleware(reg)
    dp.callback_query.outer_middleware(reg)
    dp.include_router(adminlib.build_router())
    dp.include_router(payments.build_router())
    dp.include_router(maker.build_router())

    await health_server()
    for inst in await many("SELECT * FROM bot_instances WHERE status='active'"):
        await manager.start(inst)
    asyncio.create_task(expiry_loop(manager, bot))
    try:
        await bot.delete_webhook()
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await manager.stop_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
