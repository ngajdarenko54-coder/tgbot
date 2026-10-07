import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import load_config
from .handlers import JobsHolder, router, send_due_followups
from .storage import Storage


async def followup_loop(bot: Bot, storage: Storage, jobs: JobsHolder) -> None:
    while True:
        try:
            await send_due_followups(bot, storage, jobs)
        except Exception:
            logging.exception("followup loop error")
        await asyncio.sleep(60)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    if not cfg.bot_token:
        raise SystemExit("BOT_TOKEN не задан — заполни файл .env")
    storage = Storage(cfg.db_path)
    jobs = JobsHolder(cfg.jobs_xlsx)
    active = sum(1 for j in jobs.items if j.active and j.link)
    logging.info("Загружено вакансий: %d, показываются: %d", len(jobs.items), active)
    if active == 0:
        logging.warning("Ни у одной вакансии нет ссылки (колонка link) — бот ничего не покажет")

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    dp["cfg"], dp["storage"], dp["jobs"] = cfg, storage, jobs
    asyncio.create_task(followup_loop(bot, storage, jobs))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
