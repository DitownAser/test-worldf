# Разбор дампа captures/attach_2026-10-16T09-32-03-443Z (2026-10-16)

Дата анализа: 2026-10-16. Продолжение `ATTACH_2026-10-14_FINDINGS.md`.
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

## Рекомендации по следующей записи

- Запускать `royal_capture_all_in_one.js` (или `capture_session.js`) и сразу вести
  сессию по нужному URL: `auth.getmadium.xyz/getkey/lootlabs/start` → `kys.linkvertise.lol/...`.
  До появления в `events.log` строки `RG-ENDPOINT` запись считать бесполезной —
  фильтр теперь рабочий и сработает сам.
- Держать вкладку видимой (флаги `--disable-*backgrounding*`), иначе RTDL heartbeat
  уйдёт в hidden и перехват handshake будет неполным.
- Профиль браузера с куками `usid`/`gid` adtech-цепочек тащит за собой лишние вкладки —
  для чистоты дампа использовать отдельный `--user-data-dir`.
