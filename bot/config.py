import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Минимальная загрузка .env без внешних зависимостей."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    channel_url: str
    subid_param: str
    followup_hours: int
    db_path: str
    jobs_xlsx: str


def load_config() -> Config:
    _load_dotenv()
    admins = os.getenv("ADMIN_IDS", "")
    return Config(
        bot_token=os.getenv("BOT_TOKEN", ""),
        admin_ids=frozenset(int(x) for x in admins.replace(" ", "").split(",") if x),
        channel_url=os.getenv("CHANNEL_URL", ""),
        subid_param=os.getenv("SUBID_PARAM", "sub1"),
        followup_hours=int(os.getenv("FOLLOWUP_HOURS", "48")),
        db_path=os.getenv("DB_PATH", "data/bot.db"),
        jobs_xlsx=os.getenv("JOBS_XLSX", "data/jobs.xlsx"),
    )
