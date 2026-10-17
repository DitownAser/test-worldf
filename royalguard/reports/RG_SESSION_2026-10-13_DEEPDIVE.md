# Royal Guard — полный разбор сессии 2026-10-13 (captures/logs/)

**Дата анализа:** 2026-10-16. **Источник:** `captures/logs/events.log` (51 КБ, ~300 строк),
`captures/logs/traffic.jsonl` (377 КБ, 94 запроса), `captures/page_scripts_1/` (17 файлов),
`captures/responses/`, `captures/manifest.json`. Это ЕДИНСТВЕННЫЙ дамп с полным прохождением RG-цепочки.
Проверено построчно внутри каждого файла (не грепом по именам).

---

## 1. Хронология прохождения (12:08–12:18 UTC, ~10 минут)

| t | Событие | Значение |
|---|---------|----------|
| 12:09:59 | attach к `app.getmadium.xyz/?lootlabs=credited`, 12 Next.js-чанков сохранено | пользователь уже на Madium |
| 12:10:30 | `GET auth.getmadium.xyz/account/me` → 200 | JWT + fingerprint в заголовках |
| 12:10:31 | `POST auth.getmadium.xyz/getkey/lootlabs/start` body `{}` → 200 | сервер выдаёт `{clickId, expiresAt, url}` |
| 12:10:32 | `GET kys.linkvertise.lol/DTOM/<taskGUID>` (taskID `009b16ef-…`) | страница задачи RG, inline-скрипты 0013–0016 |
| 12:10:32–35 | adblock-разведка: `probe()` грузит 10+ рекламных CDN (googlesyndication, doubleclick, taboola, outbrain, rubicon, mathtag…), DOM-эвристики по классам `.ad-container/.adsbox/…` | `[adb:final] checks=[false,false,false] detected=false in 801ms` — адблок не обнаружен |
| 12:10:33 | `POST /DTOM/<guid>` (form-urlencoded) | **PoW-решение** (см. §3) |
| 12:10:34 | редирект back → `/DTOM/<guid>?RG_Token=998cc989-…` | токен выдаётся сервером в URL; второй `RG_Token=0aa901b9-…` на `/TaskStarted/<guid>` |
| 12:10:35 | `GET /vm/Z?v=5&s=sVlRxIId4jULhDSyXYBc5HoE` → навигация main-frame | вход в ВМ-среду, session-ID `s=` в query |
| 12:10:35 | SPA-навигация `/vm/Z?data=<base64>&iframeUrl=<base64>&UserID=c5b0e80e-…&TaskID=009b16ef-…&Themid=<128 hex>` | все параметры зашифрованы base64 (не URL-safe, с `+`/`/`) |
| 12:10:35 | `GET /api/v1/securityFileID?v=<uuid>` → `GET cdn.trw.lat/rgc/cdn/756a3eed-….txt` | RGCS = «Royal-Guard YX · Yates Exchange» (консоль ссылается на `trw.lat/ds`) |
| 12:10:36 | **inline-скрипт 0024 = 429.3 КБ** (ядро клиента RG) + ASCII-баннер + blob-скрипт #47 (`6d76d68a-…`) | «Secure execution context online» |
| 12:10:36 | `GET /api/rg/encrypt-tunnel/PGPG?RG_Ant=<uuid>-<md5>` → 201 | handshake туннеля YX |
| 12:10:36 | `POST /api/rg/encrypt-tunnel/PGPSC?token=<64hex>&hmacv=<sid>` | обмен ключами (AES-256-GCM, X25519-параметр `x2`), «YX SECURITY CODE 🌙🍣🐧🌙» |
| 12:10:36 | `GET /api/RTDL/v4/SquareVM?RG_Socks=<uuid>` → **200 text/event-stream** | SSE-канал задач ВМ, sid `6f492a7e-…` |
| 12:10:36 | `POST /api/rg/v2/enigma/RTDL/pushToTalk?sid=6f492a7e-…` ×22 до 12:12+ | зашифрованные payload/payload2 каждые ~15 с |
| 12:10:36 | blob-iframe `a0d94da9-…` (скрипт 0025) → `GET /VMc/VGuard_v1?TID=<uuid>&TAD=<base64 1024+>` | VGuard в subframe, затем subframe → about:blank (зачистка) |
| 12:10:37 | `GET links.lootlabs.gg/s?yzgyivRm&data=<base64>&puid=c5b0e80e-…` → 200 | reward-редирект LootLabs (финал цепочки) |
| 12:11:26→12:18:15 | re-handshake PGPG+PGPSC каждые ~50–51 с (10 циклов), каждый со своим emoji-кодом | скользящий сеансовый ключ |
| 12:18:44 | **`[RGCS] RTDL handshake unresolved. [0x31]` ×2** | ошибка: SSE-рукопожатие не подтверждено |
| 12:18:48 | beforeunload → WS_ERROR → TAB_CLOSED | конец записи |

Итог по трафику: pushToTalk ×22, PGPG ×10, PGPSC ×10, всё остальное по 1–3 раза.

## 2. Протокол Royal Guard (реконструкция из дампа)

```
Madium app ──POST /getkey/lootlabs/start──▶ clickId + url(kys.linkvertise.lol/DTOM/<task>)
kys DTOM   ──adblock probe (fetch+DOM)────▶ POST /DTOM/<task>/adblock {detected:false}
kys DTOM   ──PoW (WebCrypto SHA-256)──────▶ POST /DTOM/<task> rg_pow_* ─▶ ?RG_Token=<uuid>
/vm/Z?s=   ──зашифрованный data/iframeUrl/UserID/TaskID/Themid──▶ ядро 429KB inline
/api/v1/securityFileID ─▶ cdn.trw.lat/rgc/cdn/<uuid>.txt   (RGCS конфиг «Yates Exchange»)
PGPG?RG_Ant=<uuid>-<hash> ─▶ 201        (init key-exchange)
PGPSC?token=<64hex>&hmacv=<sid> ◀▶ {encrypted,troubleshooter,yx_cipher:"AES-256-GCM",x2:<64hex>}
GET /api/RTDL/v4/SquareVM?RG_Socks=<uuid> ─▶ SSE (text/event-stream), ответ: x-rg-subwschannelstatus: encrypted!
POST /api/rg/v2/enigma/RTDL/pushToTalk?sid=<sse-sid> ◀▶ {payload,payload2,uuid,anti-tamper:true}  (~каждые 15 с)
blob iframe ─▶ GET /VMc/VGuard_v1?TID=&TAD=<base64> ─▶ about:blank
links.lootlabs.gg/s?...&puid=<UserID> ─▶ reward
```

### Идентификация/антиспуфинг-заголовки (все уникальны для RG)
- **Запросы:** `x-rg-anticloudflarech: <sid hmacv>` (= текущий сеансовый id!),
  `x-rg-hostingswitchuid: <128 hex, константа сессии>`, `x-rg-mosquitosbothers: <uuid>-<md5>`.
- **Ответы:** `x-rg-secureconnection`, `x-rg-subwschannelstatus: encrypted!`;
  в HTML-ответе DTOM: `access-control-expose-headers: X-RG-AntiConfig, X-RG-CacheID, X-RG-Health,
  x-RG-CloudflareChannel, x-RG-MiniTLSHandlerID, x-RG-SecureConnection, x-RG-TorNetworkHandler`.
- **Cookies:** `RoyalGuard_LatexCookie-NotATrackerBTW=<base64 344 б>` и Flask-style `session=.eJw…`
  (видны в `x-forwarded-cookie` эхо-заголовке сервера) — серверный session привязан к браузеру.
- Query-токены: `RG_Token`, `RG_Socks`, `RG_Ant` — все обычные UUIDv4, **не шифруются**.

## 3. PoW-формула (наглядно видна в POST #13)

```
rg_pow_prefix = 88b34693e5f3be95f8eae2e5725ac283   (32 hex — задача от страницы?)
rg_pow_exp    = 1791893612                          (unixtime, дедлайн = start+180 c)
rg_pow_diff   = 4.5                                 (сложность)
rg_pow_sig    = 2e01996016eab5bd…ec9a3              (64 hex = SHA-256 решение)
rg_pow_nonce  = 254624
rg_csrf       = 1791893432:4223d3a296bfaa1a8b1d657c02db2b7c.88de1f9565b51a71947d
```
Гипотеза проверки сервером: `SHA-256(prefix + nonce)` имеет ≥4.5 «сложных» единиц
(например, префикс нулей в hex при floor(diff)=4 ⇒ `2e01…` не подходит под «нули» — значит
критерий другой: вероятно старшие биты канонического порядка или счёт по алфавиту hex-цифр;
либо sig = SHA-256(prefix||nonce||exp)). Для уточнения нужен исходник PoW-скрипта (см. §5).

## 4. Крипто-слой (из тел запросов)

- PGPSC request: `{"encrypted":<base64 ~108 б>, "troubleshooter":"<uuid>-<md5>", "yx_cipher":"AES-256-GCM", "x2":"<64 hex>"}`
  → `x2` почти наверняка **публичный ключ X25519** клиента (согласуется с ранее найденным
  `deriveBits X25519` в отчёте 14.10); `encrypted` = AES-GCM(salt/config), 108 б ≈ 12 IV + 92 ct + 16 tag.
- pushToTalk: `{payload:<base64 ~100 б>, uuid:<uuid>-<md5>, anti-tamper:true, payload2:<base64 ~2× длиннее>}` —
  два буфера = heartbeat + результат ВМ-задачи. Тела ответов SquareVM(SSE)/pushToTalk в дампе **НЕ записаны**
  (capture писал только request-side + response headers) — это критичный пробел.
- Эмодзи-«SECURITY CODE» — визуальный proof-of-personality канала, меняется при каждом re-handshake.

## 5. Что НЕ попало в дамп (пробелы инструментовки)

1. **Тела ответов API** (SSE-поток SquareVM — самое ценное!). В traffic.jsonl у RESPONSE есть только
   `requestId/status/mimeType/headers/timing`. Нужен `Network.getResponseBody` по `loadingFinished`.
2. **Файлы скриптов RG.** manifest.json/`page_scripts_1/` содержат только чанки getmadium + RSC-payload
   (17 файлов). Сохранённые в events.log файлы 0013–0026 (включая ядро 0024_inline_script 429 KB,
   vm/Z 0020–0023, blob 0025) физически отсутствуют в репозитории — папка `scripts/` не доехала.
3. **inline/base64 документ DTOM и /vm/Z** (HTML) — не сохранялись.
4. Финальный reward-state LootLabs после 12:18 (сессия оборвалась ошибкой `[0x31]`).

## 6. Следствие ошибки [0x31]

Последние 2 минуты: pushToTalk идёт, но SSE-подтверждение не приходит → «RTDL handshake unresolved [0x31]».
Вероятно, capture-инструмент (CDP-attach ко всем целям + расширение `cimiefiiaegbelhefglklhhakcgmhkai`)
сам замедлил/нарушил тайминг heartbeat, либо вкладка была свёрнута ([LBS-F] visibility hidden=true несколько раз)
и браузер троттлил фоновые fetch. Это же объясняет отсутствие финального зачисления.
Вывод: **для записи RG не сворачивать вкладку и по возможности отключить лишние расширения.**

## 7. План следующего захвата (приоритет)

1. Патч capture: логировать `Network.getResponseBody` (base64) для mime ∈ {application/json, text/event-stream, text/html}
   с хостов `kys.linkvertise.lol`, `auth.getmadium.xyz`, `cdn.trw.lat`, `links.lootlabs.gg` + live-выгрузка SSE.
2. Сохранять inline-scripts в `scripts/` и коммитить всю папку captures (сейчас теряется ядро 0024).
3. Перехват WebCrypto внутри страницы /vm/Z (hook digest/DH) — сопоставить `x2`/`rg_pow_sig` с примитивами.
4. Держать вкладку RG активной до появления `resp` с финальным статусом LootLabs; контролировать `tail -f events.log | grep -E "SquareVM|0x31"`.

## 8. Артефакты-маркеры для фильтров (обновить royal_capture_all_in_one.js)

URL: `/DTOM/`, `/TaskStarted/`, `/vm/Z`, `/vm/q`, `/api/rg/encrypt-tunnel/(PGPG|PGPSC)`,
`/api/RTDL/v4/SquareVM`, `/api/rg/v2/enigma/RTDL/pushToTalk`, `/VMc/VGuard_v1`, `/api/v1/securityFileID`,
`cdn.trw.lat/rgc/`, `links.lootlabs.gg/s`.
Заголовки: `x-rg-*`, cookie `RoyalGuard_LatexCookie*`. Консоль: `[RGCS]`, `[adb:` , `[LBS`, `TEMP]: Hashing`.
