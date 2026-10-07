import html
import logging
import shutil
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import texts
from .config import Config
from .jobs import Answers, Job, load_jobs, match_jobs
from .storage import Storage

log = logging.getLogger(__name__)
router = Router()

CATEGORY_NAMES = {
    "courier": "Курьер", "warehouse": "Склад", "shifts": "Подработка сменами",
    "food": "Общепит", "office": "Офис / колл-центр", "remote": "Удалёнка",
    "field": "Разъездная работа", "master": "Мастер / услуги", "driver": "Водитель",
    "sales": "Продажи / агент",
}
AGES = [("До 18", 0), ("18–20", 18), ("21–25", 21), ("26–35", 26), ("36+", 36)]
HOURS = [("До 10 часов", 10), ("10–20 часов", 20), ("20–40 часов", 40), ("Больше 40", 60)]
SCHEDULES = [("Гибкий / подработка", "flex"), ("2/2", "2/2"), ("5/2", "5/2"), ("Ночные смены", "night"),
             ("Полный день", "full"), ("Вахта", "vahta"), ("Неважно", "any")]
REMOTE = [("Только удалённо", "only"), ("Только на месте", "no"), ("Неважно", "any")]
# В категориях, где удалёнка может быть, спрашиваем отдельно; в остальных вопрос лишний.
ASK_REMOTE_FOR = {"any", "office", "sales"}


class Form(StatesGroup):
    age = State()
    category = State()
    license = State()
    car = State()
    hours = State()
    schedule = State()
    remote = State()


class JobsHolder:
    """Текущая база вакансий в памяти; /upload подменяет её без перезапуска."""

    def __init__(self, path: str):
        self.path = path
        self.reload()

    def reload(self, path: str | None = None) -> int:
        jobs = load_jobs(path or self.path)
        self.items: list[Job] = jobs
        self.by_id = {j.offer_id: j for j in jobs}
        return len(jobs)

    def categories(self) -> list[str]:
        cats = {c for j in self.items if j.active and j.link for c in j.categories}
        return [c for c in CATEGORY_NAMES if c in cats]


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows])


def column(options: list[tuple[str, object]], prefix: str, per_row: int = 2) -> InlineKeyboardMarkup:
    buttons = [(t, f"{prefix}:{v}") for t, v in options]
    return kb([buttons[i:i + per_row] for i in range(0, len(buttons), per_row)])


def channel_kb(cfg: Config, extra: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    if cfg.channel_url:
        rows.append([InlineKeyboardButton(text="Наш канал", url=cfg.channel_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- анкета ----------

@router.message(CommandStart())
async def start(msg: Message, state: FSMContext, storage: Storage):
    await state.clear()
    storage.log(msg.chat.id, "start")
    await msg.answer(texts.START)
    await state.set_state(Form.age)
    await msg.answer(texts.Q_AGE, reply_markup=column(AGES, "age", 3))


@router.callback_query(Form.age, F.data.startswith("age:"))
async def on_age(cb: CallbackQuery, state: FSMContext, jobs: JobsHolder, cfg: Config):
    age = int(cb.data.split(":")[1])
    await cb.answer()
    if age < 18:
        await state.clear()
        await cb.message.edit_text(texts.UNDER_18, reply_markup=channel_kb(cfg))
        return
    await state.update_data(age=age)
    await state.set_state(Form.category)
    options = [(CATEGORY_NAMES[c], c) for c in jobs.categories()] + [("Любая", "any")]
    await cb.message.edit_text(texts.Q_CATEGORY, reply_markup=column(options, "cat"))


@router.callback_query(Form.category, F.data.startswith("cat:"))
async def on_category(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(category=cb.data.split(":")[1])
    await state.set_state(Form.license)
    await cb.message.edit_text(texts.Q_LICENSE, reply_markup=kb([
        [("Нет", "lic:none"), ("Категория B", "lic:b"), ("B и C", "lic:bc")]]))


@router.callback_query(Form.license, F.data.startswith("lic:"))
async def on_license(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    lic = cb.data.split(":")[1]
    await state.update_data(license_b=lic in ("b", "bc"), license_c=lic == "bc", has_car=False)
    if lic == "none":
        await ask_hours(cb, state)
    else:
        await state.set_state(Form.car)
        await cb.message.edit_text(texts.Q_CAR, reply_markup=kb([[("Да", "car:1"), ("Нет", "car:0")]]))


@router.callback_query(Form.car, F.data.startswith("car:"))
async def on_car(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(has_car=cb.data.endswith(":1"))
    await ask_hours(cb, state)


async def ask_hours(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Form.hours)
    await cb.message.edit_text(texts.Q_HOURS, reply_markup=column(HOURS, "hrs"))


@router.callback_query(Form.hours, F.data.startswith("hrs:"))
async def on_hours(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(hours=int(cb.data.split(":")[1]))
    await state.set_state(Form.schedule)
    await cb.message.edit_text(texts.Q_SCHEDULE, reply_markup=column(SCHEDULES, "sch"))


@router.callback_query(Form.schedule, F.data.startswith("sch:"))
async def on_schedule(cb: CallbackQuery, state: FSMContext, jobs: JobsHolder, cfg: Config, storage: Storage):
    await cb.answer()
    await state.update_data(schedule=cb.data.split(":", 1)[1])
    data = await state.get_data()
    if data["category"] in ASK_REMOTE_FOR:
        await state.set_state(Form.remote)
        await cb.message.edit_text(texts.Q_REMOTE, reply_markup=column(REMOTE, "rem", 1))
    else:
        await show_results(cb, state, jobs, cfg, storage)


@router.callback_query(Form.remote, F.data.startswith("rem:"))
async def on_remote(cb: CallbackQuery, state: FSMContext, jobs: JobsHolder, cfg: Config, storage: Storage):
    await cb.answer()
    await state.update_data(remote=cb.data.split(":")[1])
    await show_results(cb, state, jobs, cfg, storage)


def job_card(job: Job) -> str:
    e = html.escape
    pay = f"\n\n💰 {e(job.pay_text)}" if job.pay_text else ""
    return texts.JOB_CARD.format(title=e(job.title), description=e(job.description), pay=pay,
                                 requirements=e(job.requirements or "паспорт"))


async def show_results(cb: CallbackQuery, state: FSMContext, jobs: JobsHolder, cfg: Config, storage: Storage):
    data = await state.get_data()
    await state.clear()
    answers = Answers(**{k: v for k, v in data.items() if k in Answers.__dataclass_fields__})
    found = match_jobs(jobs.items, answers)
    storage.log(cb.message.chat.id, "finished" if found else "nothing")
    again = [[InlineKeyboardButton(text="Пройти анкету заново", callback_data="restart")]]
    if not found:
        await cb.message.edit_text(texts.NOTHING, reply_markup=channel_kb(cfg, again))
        return
    head = texts.FOUND
    if answers.relaxed:
        head = texts.RELAXED.format(what=", ".join(texts.RELAX_NAMES[r] for r in answers.relaxed)) + "\n\n" + head
    await cb.message.edit_text(head)
    for job in found:
        storage.log(cb.message.chat.id, "shown", job.offer_id)
        await cb.message.answer(job_card(job), reply_markup=kb([[("Откликнуться", f"apply:{job.offer_id}")]]))
    await cb.message.answer("Не то, что искал?", reply_markup=channel_kb(cfg, again))


@router.callback_query(F.data == "restart")
async def restart(cb: CallbackQuery, state: FSMContext, storage: Storage):
    await cb.answer()
    await state.clear()
    await state.set_state(Form.age)
    await cb.message.answer(texts.Q_AGE, reply_markup=column(AGES, "age", 3))


# ---------- отклик и сопровождение ----------

@router.callback_query(F.data.startswith("apply:"))
async def on_apply(cb: CallbackQuery, jobs: JobsHolder, storage: Storage, cfg: Config):
    await cb.answer()
    job = jobs.by_id.get(int(cb.data.split(":")[1]))
    if not job or not job.active or not job.link:
        await cb.message.answer("Эта вакансия уже закрыта. Пройди анкету ещё раз — /start")
        return
    chat_id = cb.message.chat.id
    storage.log(chat_id, "apply", job.offer_id)
    url = job.link_with_subid(cfg.subid_param, storage.user_code(chat_id))
    await cb.message.answer(texts.APPLY.format(title=html.escape(job.title)), reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Перейти к анкете работодателя", url=url)]]))
    guide = [texts.GUIDE_COMMON] + [texts.GUIDE_BY_CATEGORY[c] for c in sorted(job.categories)
                                    if c in texts.GUIDE_BY_CATEGORY]
    await cb.message.answer("\n\n".join(guide))
    await cb.message.answer(texts.ASK_REMIND, reply_markup=kb([[
        ("Да, напомни", f"remind:{job.offer_id}:1"), ("Не надо", f"remind:{job.offer_id}:0")]]))


@router.callback_query(F.data.startswith("remind:"))
async def on_remind(cb: CallbackQuery, storage: Storage, cfg: Config):
    await cb.answer()
    _, offer_id, yes = cb.data.split(":")
    if yes == "1":
        storage.add_followup(cb.message.chat.id, int(offer_id), cfg.followup_hours, stage=1)
        await cb.message.edit_text(texts.REMIND_ON)
    else:
        await cb.message.edit_text(texts.REMIND_OFF)


def followup_kb(offer_id: int, stage: int) -> InlineKeyboardMarkup:
    if stage == 2:
        return kb([[("Всё отлично", f"fu:working:{offer_id}")],
                   [("Не подошло, ищу другое", f"fu:failed:{offer_id}")]])
    return kb([[("Позвали на собеседование", f"fu:called:{offer_id}")],
               [("Уже работаю", f"fu:working:{offer_id}")],
               [("Ещё не звонили", f"fu:notcalled:{offer_id}")],
               [("Не получилось", f"fu:failed:{offer_id}")]])


async def send_due_followups(bot: Bot, storage: Storage, jobs: JobsHolder) -> None:
    for chat_id, offer_id, stage in storage.due_followups():
        storage.remove_followup(chat_id, offer_id)
        job = jobs.by_id.get(offer_id)
        title = job.title if job else "вакансия"
        template = texts.FOLLOWUP_2 if stage == 2 else texts.FOLLOWUP_1
        try:
            await bot.send_message(chat_id, template.format(title=html.escape(title)),
                                   reply_markup=followup_kb(offer_id, stage))
            storage.log(chat_id, f"followup{stage}", offer_id)
            if stage == 1:
                # если не ответит — ещё одна попытка через сутки
                storage.add_followup(chat_id, offer_id, 24, stage=3)
        except Exception as e:  # пользователь заблокировал бота и т.п.
            log.warning("followup to %s failed: %s", chat_id, e)


@router.callback_query(F.data.startswith("fu:"))
async def on_followup(cb: CallbackQuery, storage: Storage, cfg: Config):
    await cb.answer()
    _, answer, offer_id = cb.data.split(":")
    offer_id = int(offer_id)
    chat_id = cb.message.chat.id
    storage.remove_followup(chat_id, offer_id)
    storage.log(chat_id, f"fu_{answer}", offer_id)
    again = [[InlineKeyboardButton(text="Подобрать другое", callback_data="restart")]]
    if answer == "called":
        storage.add_followup(chat_id, offer_id, 24 * 7, stage=2)
        await cb.message.edit_text(texts.FU_CALLED)
    elif answer == "working":
        await cb.message.edit_text(texts.FU_WORKING, reply_markup=channel_kb(cfg))
    elif answer == "notcalled":
        storage.add_followup(chat_id, offer_id, 48, stage=3)
        await cb.message.edit_text(texts.FU_NOT_CALLED, reply_markup=channel_kb(cfg, again))
    else:
        await cb.message.edit_text(texts.FU_FAILED, reply_markup=channel_kb(cfg, again))


# ---------- служебные команды ----------

@router.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(texts.HELP)


@router.message(Command("delete"))
async def delete_cmd(msg: Message, state: FSMContext, storage: Storage):
    await state.clear()
    storage.delete_user(msg.chat.id)
    await msg.answer(texts.DELETED)


@router.message(Command("stop_reminders"))
async def stop_reminders(msg: Message, storage: Storage):
    storage.db.execute("DELETE FROM followups WHERE chat_id=?", (msg.chat.id,))
    storage.db.commit()
    await msg.answer(texts.REMINDERS_STOPPED)


@router.message(Command("stats"))
async def stats_cmd(msg: Message, storage: Storage, cfg: Config, jobs: JobsHolder):
    if msg.from_user.id not in cfg.admin_ids:
        return
    s = storage.stats(30)
    k = s["kinds"]
    lines = [
        "<b>За 30 дней (уникальные пользователи)</b>",
        f"Начали анкету: {k.get('start', 0)}",
        f"Получили вакансии: {k.get('finished', 0)}",
        f"Ничего не нашлось: {k.get('nothing', 0)}",
        f"Нажали «Откликнуться»: {k.get('apply', 0)}",
        f"Позвали на собеседование: {k.get('fu_called', 0)}",
        f"Вышли на работу: {k.get('fu_working', 0)}",
        "", "<b>Отклики по офферам</b>",
    ]
    for offer_id, n in s["apply_by_offer"]:
        job = jobs.by_id.get(offer_id)
        lines.append(f"{offer_id} {job.title if job else ''}: {n}")
    await msg.answer("\n".join(lines))


@router.message(Command("upload"))
async def upload_help(msg: Message, cfg: Config):
    if msg.from_user.id in cfg.admin_ids:
        await msg.answer("Пришли файл jobs.xlsx документом — я проверю его и обновлю базу.")


@router.message(F.document)
async def upload_file(msg: Message, bot: Bot, cfg: Config, jobs: JobsHolder):
    if msg.from_user.id not in cfg.admin_ids:
        return
    if not (msg.document.file_name or "").lower().endswith(".xlsx"):
        await msg.answer("Нужен файл .xlsx")
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "jobs.xlsx"
        await bot.download(msg.document, destination=path)
        try:
            n = jobs.reload(str(path))
        except Exception as e:
            await msg.answer(f"Файл не принят, база не изменилась.\n{e}")
            return
        shutil.copy(path, cfg.jobs_xlsx)
    active = sum(1 for j in jobs.items if j.active and j.link)
    await msg.answer(f"База обновлена: {n} вакансий, показываются {active} (активные и со ссылкой).")
