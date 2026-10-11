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

## Если сервер в РФ и Telegram недоступен

Проверка: `curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://api.telegram.org` — если `000` или таймаут, нужен прокси.

**Вариант 1 — купленный прокси (так сейчас работает бот).** Серверный индивидуальный IPv4-прокси в Европе, HTTP или SOCKS5. Проверка: `curl -sS -m 15 -x http://ЛОГИН:ПАРОЛЬ@IP:ПОРТ -o /dev/null -w "%{http_code}\n" https://api.telegram.org` → `302`. В `.env`: `TELEGRAM_PROXY=http://ЛОГИН:ПАРОЛЬ@IP:ПОРТ` (или `socks5://...`), затем `systemctl restart tgbot`.

**Вариант 2 — свой туннель через зарубежный сервер:**

1. Арендуй самый дешёвый сервер за рубежом (Ubuntu). Устанавливать на нём ничего не нужно, нужен только вход по SSH под root.
2. На сервере с ботом:
```bash
cd ~/tgbot && git pull && .venv/bin/pip install -r requirements.txt
bash deploy/setup_tunnel.sh IP_ЗАРУБЕЖНОГО_СЕРВЕРА
```
3. В `.env` добавь `TELEGRAM_PROXY=socks5://127.0.0.1:1080` и запусти бота.

Данные пользователей остаются на сервере в РФ, через зарубежный сервер идут только зашифрованные запросы к Telegram. Туннель работает как служба `tg-tunnel` и сам переподключается.

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
