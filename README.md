# Бот подбора подработки (Екатеринбург, 18+)

Анкета из 5–6 вопросов → подбор вакансий из `data/jobs.xlsx` → отклик по партнёрской ссылке Pampadu с субайди → подсказки по трудоустройству → напоминания «как дела» через 2 дня и через неделю.

Бот не собирает имя и телефон. Хранится только chat_id (чтобы писать напоминания, на которые человек согласился), случайный код для субайди и обезличенная статистика. Команда `/delete` удаляет данные пользователя.

## Перед запуском

1. В `data/jobs.xlsx` заполни колонки `link` (партнёрские ссылки) и `pay_text` (текст о доходе). **Вакансия без ссылки не показывается.**
2. Уточни у менеджера Pampadu, как называется параметр субайди в ссылках, и впиши его в `SUBID_PARAM` (по умолчанию `sub1`).
3. Создай бота в @BotFather и получи токен.

## Запуск на VPS (Ubuntu)

```bash
sudo apt update && sudo apt install -y python3-venv git
git clone https://github.com/ngajdarenko54-coder/tgbot.git
cd tgbot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env        # вписать BOT_TOKEN, ADMIN_IDS, CHANNEL_URL
.venv/bin/python -m bot     # проверка: напиши боту /start, остановить — Ctrl+C
```

### Автозапуск (работает 24/7, перезапускается после сбоев)

```bash
sudo tee /etc/systemd/system/tgbot.service > /dev/null <<EOF
[Unit]
Description=Job bot
After=network-online.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python -m bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now tgbot
journalctl -u tgbot -f      # смотреть логи
```

### Обновление кода

```bash
cd tgbot && git pull && sudo systemctl restart tgbot
```

## Команды

| Команда | Кто | Что делает |
|---|---|---|
| `/start` | все | анкета и подбор |
| `/stop_reminders` | все | отключить напоминания |
| `/delete` | все | удалить свои данные |
| `/help` | все | список команд |
| `/upload` + файл `.xlsx` | админ | заменить базу вакансий без перезапуска (файл проверяется перед заменой) |
| `/stats` | админ | воронка за 30 дней и отклики по офферам |

## Где что править

- Тексты бота — `bot/texts.py`.
- Вакансии и фильтры — `data/jobs.xlsx`, описание полей на листе «Справочник».
- Логика подбора — `bot/jobs.py` (`match_jobs`): жёсткие фильтры (возраст, права, авто, категория) не ослабляются; если ничего не нашлось, по очереди снимаются район, график, часы.

## Тесты

```bash
.venv/bin/pip install pytest && .venv/bin/python -m pytest -q
```
