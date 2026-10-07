"""Sub-botlarni bir jarayonda parallel ishga tushiruvchi menejer."""
import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage

import adminlib
import kino
import music
import contest
import payments
import support
import subcommon
from db import ex
from middleware import Gate

log = logging.getLogger("manager")


def build_dispatcher(inst):
    dp = Dispatcher(storage=MemoryStorage(), bot_id=inst["id"], btype=inst["type"])
    gate = Gate()
    dp.message.outer_middleware(gate)
    dp.callback_query.outer_middleware(gate)
    dp.include_router(adminlib.build_router())
    dp.include_router(payments.build_router())
    dp.include_router(subcommon.build_router())
    mod = {"kino": kino, "music": music, "support": support, "contest": contest}[inst["type"]]
    dp.include_router(mod.build_router())
    return dp


class Manager:
    def __init__(self):
        self.tasks = {}

    async def start(self, inst):
        if inst["id"] in self.tasks and not self.tasks[inst["id"]].done():
            return
        bot = Bot(inst["token"], default=DefaultBotProperties(parse_mode="HTML"))
        dp = build_dispatcher(inst)
        self.tasks[inst["id"]] = asyncio.create_task(self._poll(inst["id"], bot, dp))
        log.info("Sub-bot ishga tushdi: #%s @%s", inst["id"], inst["username"])

    async def _poll(self, iid, bot, dp):
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot, handle_signals=False, allowed_updates=dp.resolve_used_update_types())
        except asyncio.CancelledError:
            raise
        except TelegramUnauthorizedError:
            await ex("UPDATE bot_instances SET status='invalid' WHERE id=?", (iid,))
            log.warning("Sub-bot #%s tokeni yaroqsiz", iid)
        except Exception:
            log.exception("Sub-bot #%s to'xtadi", iid)
        finally:
            with contextlib.suppress(Exception):
                await bot.session.close()

    async def stop(self, iid):
        t = self.tasks.pop(iid, None)
        if t:
            t.cancel()
            with contextlib.suppress(BaseException):
                await t

    async def stop_all(self):
        for iid in list(self.tasks):
            await self.stop(iid)
