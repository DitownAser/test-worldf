# Полный гайд: royal_capture_all_in_one.js
Захват всей сессии Royal Guard (включая «промежуточки» Linkvertise/LootLabs) из **уже запущенного** браузера через DevTools-протокол.

Скрипт лежит здесь:
```
royalguard/scripts/royal_capture_all_in_one.js
```
Он состоит из двух секций в одном файле:
- **СЕКЦИЯ A — crypto_hijack** (внедряется в каждую страницу как init-script ДО загрузки): перехват SubtleCrypto (ключи, IV, plaintext RTDL), WebAssembly (дамп .wasm SquareVM + границы ВМ↔JS), fetch/XHR/sendBeacon, анти-анти-отладка (disguise).
- **СЕКЦИЯ B — CDP-раннер** (Node): подключается к Chrome на debug-порт, цепляется ко ВСЕМ открытым вкладкам и автоматически ловит НОВЫЕ вкладки (`Target.setDiscoverTargets` / `targetCreated`), пишет всё в папку захвата.

---

## Шаг 0. Требования
- Node.js 18+ и npm.
- Google Chrome / Chromium / Brave / Edge (любой Chromium-браузер ≥ 100).
- Зависимость `chrome-remote-interface`:
```bash
cd royalguard
npm i                      # или: npm i chrome-remote-interface
```

## Шаг 1. Запусти браузер с debug-портом
⚠️ Сначала **полностью закрой все окна Chrome** (проверь в диспетчере задач, чтобы не осталось процессов) — иначе флаг порта проигнорируется, т.к. порт слушает только впервые запущенный процесс.

**Windows (cmd):**
```bat
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir=C:\chrome-dbg ^
  --disable-backgrounding-occluded-windows ^
  --disable-renderer-backgrounding ^
  --disable-background-timer-throttling
```

**Linux:**
```bash
google-chrome-stable \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-dbg \
  --disable-backgrounding-occluded-windows \
  --disable-renderer-backgrounding \
  --disable-background-timer-throttling &
```

**macOS:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-dbg \
  --disable-backgrounding-occluded-windows \
  --disable-renderer-backgrounding \
  --disable-background-timer-throttling &
```

Зачем флаги:
- `--remote-debugging-port=9222` — CDP-эндпоинт, к которому цепляется скрипт.
- `--user-data-dir=...` — отдельный профиль; без него Chrome может не открыть порт (политика «default profile»). Плюс это чистый профиль: сессия/куки Royal Guard начнутся с нуля.
- Три `--disable-*` флага — Royal Guard следит за `visibility` вкладки (RTDL). Если ты свернёшь/затенишь окно, сайт уйдёт в "hidden" и handshake оборвётся. С этими флагами фоновые вкладки не троттлятся.

Проверка, что порт живой:
```bash
curl http://127.0.0.1:9222/json/version
```
Должен вернуть JSON с `webSocketDebuggerUrl`.

## Шаг 2. Открой сайт в этом браузере
В открытом браузере зайди на royalgueard и дойди до нужного rewards/заказа — туда, где начинаются промежуточные страницы (Madium → linkvertise.lol → iframe lootlabs и т.п.). Можно начать клики сразу — скрипт подключится к уже идущей сессии; главное, чтобы новые вкладки открывались после запуска скрипта (шаг 3) — они будут перехвачены автоматически вместе с init-script'ом.

## Шаг 3. Запусти захват
```bash
cd royalguard/scripts
node royal_capture_all_in_one.js            # порт 9222 по умолчанию
node royal_capture_all_in_one.js 9333       # свой порт (или DEBUG_PORT=9333)
RECORD_SEC=600 node royal_capture_all_in_one.js   # автостоп через 10 минут
DUMP_INTERVAL_MS=5000 node royal_capture_all_in_one.js  # чаще сливать hijack-дамп (по умолч. 10000)
```
В консоли появится:
```
[attach] Пишу всё в: .../royalguard/captures/attach_<дата>/
[attach] Подключено вкладок: N. Кликай по сайту. Останов — Ctrl-C.
```

## Шаг 4. Пройди все «промежуточки» руками
Кликай по сайту до самого конца цепочки (реклама, таймеры, капча — всё вручную; автоматизировать это нельзя, Linkvertise/LootLabs требуют человеческие проверки). Скрипт в это время пишет всё в фоне. Новые вкладки/табы цепляются автоматически, и на каждую crypto_hijack навешивается **до** загрузки страницы.

Советы:
- Не сворачивай окно (лучше просто держи поверх других окон).
- Не закрывай вкладки промежуточных сайтов до остановки записи — их дампы собираются каждые 10 сек и при остановке.
- Когда прошла всю цепочку до финальной страницы/кода — жми **Ctrl-C** в терминале со скриптом. Он сделает финальный сбор `hijack_structured.json` и напишет:
```
[attach] Готово. Запросов: N. Дамп в: .../captures/attach_<дата>/
```

## Шаг 5. Что где лежит (результат)
Папка: `royalguard/captures/attach_<ISO-дата>/`

| Файл | Содержимое |
|---|---|
| `traffic.jsonl` | Все запросы/ответы со всех вкладок: url, method, headers, статус, тела (≤1.5 МБ), привязка к вкладке |
| `events.log` | Консоль страниц, события, RG-ENDPOINT, WASM-SAVED, SESSION-START/END |
| `crypto.jsonl` | Перехваты crypto_hijack: generateKey/importKey/deriveBits/encrypt/decrypt — алгоритмы, ключи, IV, ciphertext и **готовый plaintext RTDL** |
| `scripts/` | Исходники страниц и inline-скрипты каждой вкладки |
| `wasm/` | Дампнутые .wasm-модули SquareVM |
| `responses/` | Тела ответов по RG-эндпоинтам |
| `hijack_structured.json` | Итоговый структурированный дамп первой непустой вкладки (все crypto/wasm/net-события разом) |

Быстрый разбор (JSONL = по одному JSON в строке):
```bash
# все AES-операции с ключами:
grep '"subtle"' captures/attach_*/crypto.jsonl | head

# эндпоинты RTDL/Royal Guard:
grep -o '"url":"[^"]*"' captures/attach_*/traffic.jsonl | sort -u | grep -i 'rtdl\|royal\|linkvertise\|lootlabs'

# plaintext RTDL (до/после encrypt):
grep 'plaintextB64\|rtdl' captures/attach_*/crypto.jsonl
```

## Частые проблемы
| Симптом | Причина / решение |
|---|---|
| `Не могу подключиться к Chrome на порту 9222` | Браузер запущен без флага порта или уже был открыт другой экземпляр. Полностью закрой Chrome и повтори шаг 1. Проверь `curl http://127.0.0.1:9222/json/version`. |
| Пустой `crypto.jsonl` | Страница загружена ДО подключения и использовала ранний кэш subtle-объектов, либо шифрование идёт внутри WASM (тогда смотри `wasm/` и `traffic.jsonl`). Перезапусти запись и пройди цепочку заново — init-script гарантированно ставится до загрузки новых таргетов. |
| Handshake обрывается на середине | Окно было свёрнуто/скрыто → visibility:hidden. Не минимизируй; используй три `--disable-*` флага. |
| `Cannot find module 'chrome-remote-interface'` | `cd royalguard && npm i`. |
| Порт занят / другая версия Chrome | Используй другой порт: `node royal_capture_all_in_one.js 9333` + тот же порт в флаге запуска браузера. |
| Linux: порт не слушается под root | Не запускай Chrome от root без `--no-sandbox` (добавь флаг, если пришлось). |
| Очень большой `traffic.jsonl` | Тела >1.5 МБ не пишутся (защита от OOM); при необходимости уменьши `MAX_BODY_BYTES` в скрипте. |

## Короткий чек-лист
1. Закрыть весь Chrome.
2. Запустить Chrome с `--remote-debugging-port=9222 --user-data-dir=... --disable-*-throttling`.
3. Открыть royalgueard, дойти до цепочки промежуток.
4. `node royal_capture_all_in_one.js`
5. Пройти всю цепочку руками, не сворачивая окно.
6. Ctrl-C → забрать `royalguard/captures/attach_<дата>/`.
