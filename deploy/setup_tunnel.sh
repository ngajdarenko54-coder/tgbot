#!/usr/bin/env bash
# Туннель к Telegram через зарубежный сервер.
# Запускать на сервере с ботом (в РФ):  bash deploy/setup_tunnel.sh IP_ЗАРУБЕЖНОГО_СЕРВЕРА
# На зарубежном сервере ничего устанавливать не нужно — достаточно входа по SSH под root.
set -e
REMOTE="$1"
if [ -z "$REMOTE" ]; then
  echo "Использование: bash deploy/setup_tunnel.sh IP_ЗАРУБЕЖНОГО_СЕРВЕРА"; exit 1
fi
KEY=/root/.ssh/tg_tunnel
mkdir -p /root/.ssh && chmod 700 /root/.ssh
[ -f "$KEY" ] || ssh-keygen -t ed25519 -N "" -f "$KEY" -q

echo
echo ">>> Сейчас спросит пароль root от зарубежного сервера ($REMOTE). Ввод невидимый — вставь и нажми Enter."
ssh-copy-id -i "$KEY.pub" -o StrictHostKeyChecking=accept-new root@"$REMOTE"

cat > /etc/systemd/system/tg-tunnel.service <<EOF
[Unit]
Description=SOCKS-туннель к Telegram через $REMOTE
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh -N -D 127.0.0.1:1080 -i $KEY -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new root@$REMOTE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tg-tunnel
sleep 3
CODE=$(curl -sS -m 15 --socks5-hostname 127.0.0.1:1080 -o /dev/null -w "%{http_code}" https://api.telegram.org || true)
if [ "$CODE" = "302" ] || [ "$CODE" = "200" ]; then
  echo
  echo "ГОТОВО: Telegram доступен через туннель (код $CODE)."
  echo "Теперь впиши в .env строку:  TELEGRAM_PROXY=socks5://127.0.0.1:1080"
else
  echo
  echo "ОШИБКА: туннель не работает (код $CODE). Пришли вывод команды:  journalctl -u tg-tunnel -n 30 --no-pager"
fi
