#!/usr/bin/env bash
# capture.sh — быстрый запуск захвата (Linux).
#   ./capture.sh                 # порт 9222, автозапуск Chrome если порт свободен
#   ./capture.sh 9333            # свой порт
#   RECORD_SEC=1800 ./capture.sh # автостоп через 30 мин
#   START_URL="https://auth.getmadium.xyz/getkey/lootlabs/start" ./capture.sh
set -e
cd "$(dirname "$0")"
PORT="${1:-9222}"

echo "== проверка порта $PORT =="
if curl -s -m 2 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  echo "✔ порт слушается: $(curl -s -m 2 http://127.0.0.1:$PORT/json/version | grep -oP '(?<="Browser":")[^"]+')"
else
  echo "✘ порт свободен — royal_capture_all_in_one.js сам поднимет браузер"
fi

# live-мониторинг RG-ENDPOINT из events.log новой сессии
( sleep 5
  LOGF=$(ls -t ../captures/attach_*/events.log 2>/dev/null | head -1)
  [ -n "$LOGF" ] && tail -n +1 -f "$LOGF" | grep --line-buffered -E "RG-ENDPOINT|WASM-SAVED|RG-RESP-SAVED|BROWSER-AUTO-LAUNCH" &
) &
MON=$!
trap 'kill $MON 2>/dev/null' EXIT

node royal_capture_all_in_one.js "$PORT"
