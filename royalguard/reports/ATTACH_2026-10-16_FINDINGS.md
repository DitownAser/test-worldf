# Разбор дампа captures/attach_2026-10-16T09-32-03-443Z (2026-10-16)

Дата анализа: 2026-10-16. Продолжение `ATTACH_2026-10-14_FINDINGS.md`.

> **УТОЧНЕНИЕ v2 (после глубокой проверки каждого файла дампа изнутри):**
> Пользователь подтвердил, что проходил цепочку полностью до конца.
> Посимвольная проверка ВСЕХ файлов дампа (traffic.jsonl 1536 записей,
> crypto.jsonl 1652, events.log 697, hijack_structured.json 15, все 324
> скрипта) показала: **RG-хостов в этом дампе нет, но они есть в другом
> месте репозитория** — в папке `captures/logs/` лежит полный Royal-Guard
> трафик сессии **2026-10-13 12:08–12:18 UTC** (app/auth.getmadium.xyz →
> kys.linkvertise.lol: RTDL/SquareVM/VGuard/PGPSC/PGPG, links.lootlabs.gg,
> cdn.trw.lat). То есть полное прохождение было записано ранее; дамп 10-16
> — это отдельная adtech-ветка (aucey→hai8g→litenery→winline), шедшая
> параллельно/вне CDP-сессии RG. См. разделы ниже.
Инструмент записи: `scripts/royal_capture_all_in_one.js` (тот же crypto_hijack + CDP-раннер).

## Резюме одной строкой

**Цепочка Royal Guard в этом дампе снова отсутствует.** Запись — это та же самая
ad-tech/affiliate-ветка (`cdn.aucey.com → hai8g.com → my.rtmark.net → litenery.shop
→ winline.kz`), что и 2026-10-14, но теперь **инструмент работает исправно**:
URL в `traffic.jsonl` заполнены (баг пустого `url` из 10-14 подтверждённо починен),
скрипты сохраняются с осмысленными именами, появился `hijack_structured.json`.

## Содержимое дампа

| Файл | Размер/кол-во | Комментарий |
|---|---|---|
| `traffic.jsonl` | 1536 записей (804 req / 732 resp) | все URL на месте; 12 таргетов-вкладок |
| `crypto.jsonl` | 1652 записи | только `getterAccess` 1136, `sendBeacon` 386, `installed` 79, `visibility` 51 |
| `events.log` | 697 строк | сессия 09:32:03 → 09:39:21 UTC (Ctrl-C), RG-ENDPOINT = 0 |
| `scripts/` | 324 файла | aucey/_astro бандлы, YouTube player, wyv.gg Svelte-чанки |
| `hijack_structured.json` | новый артефакт раннера | структурированный дамп hijack-событий |

Проверка на объект исследования (grep по traffic/events/crypto/hijack):
`linkvertise | kys. | getmadium | lootlabs | royalg | VGuard | RTDL | PoW` — **0 совпадений**.
Криптоперехватов нет вообще (`digest/sign/deriveBits/importKey/encrypt` = 0), wasm-дампов
нет — SquareVM не инстанцировалась, то есть страница Royal Guard даже не открывалась.

## Что реально происходило (таймлайн)

- 09:32:54 — вкладка на `wyv.gg` (витрина; логотипы платёжек, `discord-community.json`;
  рядом `myvouch.es` — Discord-аватары «доказательств», канал YouTube `@MadGo1000`).
- 09:33–09:35 — YouTube watch-страницы (`826nNW8fakw`); видеофлоу ловит 403 на
  googlevideo videoplayback (ctier=L — контент с ограничениями).
- 09:34:40 — старт affiliate-цепочки: `cdn.aucey.com/1034/ru.html?...&rdk=rk3`
  (лендинг «sweeps-survey», Astro-бандлы + телеметрия `/sync-metrics`, ~127 beacon).
- 09:36:48–09:39:08 — прогон через трекер:
  - `hai8g.com/sftouch?...&rb=<base64url-токен>` (3 раза, новые `p_rid` каждый раз);
  - `my.rtmark.net/gid.js?userId=...&set2ud=true&z=10559238&p_src=sf` + `img.gif?f=merge`
    (pixel-конверсии; `csflbck=normal_pixel` отдаёт JSON `{gid, skipSubscribe}`);
  - `litenery.shop/?click_id=...&cost=0.004250&zoneid=10559238&campaignid=11355543
    &country=KZ&isp=jsc+altel&user_activity=high...` → `detect.php` → `verify.php?_vid=..&_eid=..`
    (параметры клика полностью открытые, включая cost и useragent);
  - финальная подмена-редирект на `winline.kz/x5/` (букмекер; Nuxt-ассеты `s.winline.kz`).
- 09:39:06 — FingerprintJS v4 (`eu.api.fpjs.io`, ключ-вид `PONBWM1tJvDjA52Jopft`) прямо
  на `litenery.shop/detect.php`; его обращения к `window.crypto` — источник всех
  `getterAccess` в crypto.jsonl. Рядом стандартный adtech: `cdntechone.com/stattag.js`,
  `datatechonert.com/log/add`, `my.rtmark.net`.
- 09:39:21 — SESSION-END (ctrl-c), 804 запроса записано.

## Выводы

1. **Инструмент более пригоден**: дамп 10-16 записан уже патченным кодом
   (`request.url` вместо корневого `url`) — имена файлов восстановлены, трафик читаем.
   Это валидирует фикс бага из отчёта 14-го числа.
2. **Дамп бесполезен для основной цели** (реверс PoW/RTDL/SquareVM): цепочку
   Madium→Royal Guard никто не проходил. Hijack молчит ровно там, где должен говорить —
   это полезный негативный контроль: ложных срабатываний RG-фильтр не даёт.
3. **Побочная ценность**: полностью видна механика anti-fraud/affiliate-прокладки,
   через которую обычно идёт «человеческая» часть квеста (ucey/Astro landing → rtmark
   postback → detect/verify → advertiser). Токены `rb=` (sftouch) и `_vid/_eid`
   (verify.php) — единственные криптосигнатуры в дампе, и они не шифруются.
4. Из 324 сохранённых скриптов представляют интерес для переиспользования:
   `*_astro_detect.DC7Ee_Lb.js` (in-app/браузерные UA-детекты лендинга),
   `Adex.Ck9SET3F.js` (ad-exchange логика лендинга), `0282_d_chunk_kevlar...` (YouTube).

## Глубокая проверка каждого файла дампа 10-16 (изнутри, не grep'ом по верхам)

| Файл | Что проверено внутри | Результат |
|---|---|---|
| `traffic.jsonl` (1536 зап.) | разбор JSON построчно: 804 req / 732 resp; все 43 уникальных хоста вынесены в список; 16 Document-навигаций с таймстампами и target-ID | среди 43 хостов **нет ни одного** RG-домена; единственные Document-навигации: YouTube×2, hai8g×4, litenery×8, winline×2 |
| `crypto.jsonl` (1652 зап.) | парсинг всех ops: `getterAccess` 1136, `sendBeacon` 386, `installed` 79, `visibility` 51; href по всем `installed` | реальных crypto-операций (`digest/sign/deriveBits/importKey/encrypt`) — **0**; getterAccess стеки указывают на youtube `player_es6 base.js` и FingerprintJS, не на ВМ |
| `events.log` (697 строк) | типизация событий: 668 runtime:log (все `[HIJACK]`), 16 console:error (404 ytimg), SESSION-START/END | ни одного RG-ENDPOINT / WASM-SAVED; hijack установлен на 6 вкладках |
| `hijack_structured.json` (15 эл.) | каждый элемент прочитан: installed×(ua/href), sendBeacon→`cdn.aucey.com/sync-metrics` (adex_init телеметрия) | только лендинг-телеметрия, крипто-ВМ отсутствует |
| `scripts/` (324 файла) | инвентаризация по доменам + grep содержимого каждого файла на `linkvertise/getmadium/lootlabs/kys./RG_Token/VGuard/SquareVM` | 324 файла = aucey/_astro (~180), YouTube (~70), wyv.gg (~25), winline, fpjs, rtmark-пиксель; совпадений по RG-токенам в именах/URL — 0 (совпадения подстрок «captcha/vguard» внутри скриптов — ложные, от adtech-либ) |
| таргеты (12 target-ID) | группировка трафика по вкладкам | RG-цепочка не появлялась НИ НА ОДНОЙ из 12 вкладок зафиксированного окна |

Дополнительно: `RG_Token|RG_Socks|RG_Ant` — 0 вхождений во всех четырёх дампах 14–16 октября.

## ГЛАВНАЯ НАХОДКА: полное прохождение RG записано в `captures/logs/` (сессия 2026-10-13)

При переборе всех файлов внутри `captures/` обнаружилось, что папка `logs/`
(и сопутствующие `manifest.json`, `page_scripts_1/`, `responses/`, а также
`royalguard/js_dumps/*`) содержит ДРУГУЮ запись — старого скрипта
`capture_session.js`, датированную **13.10.2026 12:08:21–12:18:48 UTC**.
Это ровно то полное прохождение цепочки, которого не хватало:

- 12:09:59 — attach к вкладке `app.getmadium.xyz/?lootlabs=credited` (target F99F…).
- 12:10:31 — `POST auth.getmadium.xyz/getkey/lootlabs/start` → 200 JSON → редирект.
- 12:10:32 — навигация главной рамки в `kys.linkvertise.lol/DTOM/009b16ef-…`; сохранены inline-скрипты страницы (0013/0014/0016).
- 12:10:34 — POST → `?RG_Token=998cc989-…` (получение токена задачи).
- 12:10:35 — `GET cdn.trw.lat/rgc/cdn/756a3eed….txt` (200 text/plain — конфиг/RGC-загрузка); консоль `[RGCS] Royal-Guard YX · Yates Exchange`.
- 12:10:36 — `GET kys.linkvertise.lol/api/RTDL/v4/SquareVM?RG_Socks=14d19e23-…` → **200 text/event-stream** (SSE-стрим задач ВМ!) и `GET /VMc/VGuard_v1?TID=…&TAD=<base64>` (iframe VGuard).
- Далее ~8 минут цикла: `/api/rg/v2/enigma/RTDL/pushToTalk` ×22, `/api/rg/encrypt-tunnel/PGPG` ×10, `/api/rg/encrypt-tunnel/PGPSC` ×10, `/vm/Z`, `/vm/q`, blob-скрипты ВМ; консоль показывает re-handshake и «YX SECURITY CODE 🐸🐬🦖🐬» (человекочитаемый код подтверждения).
- 12:18:44–48 — `RTDL handshake unresolved [0x31]` ×2, перед закрытием вкладки ([LBS-F] visibility/beforeunload). Сессия обрывается WS_ERROR при закрытии таба — финальный reward-редирект (links.lootlabs.gg отдаёт 200 в 12:10:37) НЕ дописан в этот лог.
- Артефакты: `js_dumps/session_a_getmadium/` (12 чанков Next.js Madium), `session_b_kys/` (inline-скрипты RG-страницы), `iframe_lootlabs/` (15 файлов, до 1.1 МБ), `page_scripts_1/files/origins/<hash>/_next/...`, `manifest.json` (sha256 на каждый скрипт).

**Итог пересмотра:** «SquareVM не запускалась» верно ТОЛЬКО для дампа 10-16.
Для прохождения 10-13 она запускалась полностью (SSE SquareVM, VGuard iframe,
RTDL pushToTalk, PGP/PGPSC туннель) — это и есть основной материал исследования,
он лежит в `captures/logs/` + `js_dumps/`, а не в `attach_*` папках.

## Почему дамп 10-16 без RG, даже при «прошёл до конца»

1. Запись 10-16 охватывает 09:32–09:39 UTC и 12 вкладок одного CDP-окна; в них
   физически не было ни одного запроса к RG-доменам (см. таблицу выше) — значит
   RG-звено того прохождения открывалось вне отлаживаемого окна (второй Chrome
   без :9222 / popup нового процесса / приложение).
2. Полное же прохождение с рабочей SquareVM уже задокументировано в логах 10-13 —
   сравнивать нужно именно их с новыми попытками.

## Рекомендации по следующей записи

- Запускать `royal_capture_all_in_one.js` (или `capture_session.js`) и сразу вести
  сессию по нужному URL: `auth.getmadium.xyz/getkey/lootlabs/start` → `kys.linkvertise.lol/...`.
  До появления в `events.log` строки `RG-ENDPOINT` запись считать бесполезной —
  фильтр теперь рабочий и сработает сам.
- Держать вкладку видимой (флаги `--disable-*backgrounding*`), иначе RTDL heartbeat
  уйдёт в hidden и перехват handshake будет неполным.
- Профиль браузера с куками `usid`/`gid` adtech-цепочек тащит за собой лишние вкладки —
  для чистоты дампа использовать отдельный `--user-data-dir`.

## Почему RG не попала в дамп (гипотезы, проверено по files.log/events.log)

1. **Подмена цели.** В дампе записана совсем другая воронка: `cdn.aucey.com` (лендинг
   «sweeps-survey», AdEx/Admitad-трекинг hai8g.com + my.rtmark.net) → `litenery.shop`
   (detect.php/verify.php с FingerprintJS v4) → финальный редирект на `winline.kz/x5/`
   (букмекер). Ни одного хоста Royal Guard-цепочки за 7 минут сессии (09:32:54–09:39:20 UTC).
2. **Скрипт hijack установлен, но ВМ не запускалась.** `hijack_structured.json`: 79 событий
   `installed`, `sendBeacon` (телеметрия лендинга), `getterAccess` (FingerprintJS/YouTube трогают
   `window.crypto`). Операций `digest/sign/deriveBits/encrypt` — 0, wasm-дампов — 0. SquareVM не стартовала.
3. **Возможные причины:** страница reward проходила в другой вкладке/профиле Chrome (не тот,
   к которому подключён CDP на :9222); либо pass шёл через мобильное приложение/десктопный
   клиент; либо RG-звено открывается popup'ом нового окна Chrome без флага remote-debugging.

## Что делать при следующем прохождении «до конца»

- Запускать capture **до** открытия первой ссылки и держать его всё время прохождения.
- Проверять в реальном времени: `tail -f events.log | grep RG-ENDPOINT` — если строки нет,
  дамп снова будет бесполезен.
- Все ссылки цепочки (`auth.getmadium.xyz/getkey/lootlabs/start` → `kys.linkvertise.lol/...`)
  открывать **в том же окне**, что запущен с `--remote-debugging-port=9222`.
- Не использовать старый профиль с кучей adtech-расширений/куков — они перекрывают запись шумом.
