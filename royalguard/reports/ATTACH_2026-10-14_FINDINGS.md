# Разбор новых дампов: captures/attach_2026-10-14* (2026-10-14)

Дата анализа: 2026-10-14. Дополнение к `CAPTURES_FINDINGS.md` (дамп 2026-10-13).

## Что пришло нового в `captures/`

| Директория | Содержимое |
|---|---|
| `attach_2026-10-14T11-04-57-541Z/` | Пустая запись (traffic/crypto = 0 байт). Chrome на момент запуска ещё не имел page-таргетов (`SESSION-START targets:0`) — сессия брошена, ценности нет. |
| `attach_2026-10-14T11-57-01-853Z/` | Полная attach-сессия: трафик 2075 строк (~1029 запросов), `crypto.jsonl` 2904 записи, `events.log`, 435 сохранённых скриптов (6.1 МБ). Сессия 11:57→12:01 UTC, остановлена Ctrl-C. |

## Главный вывод: цепочка Royal Guard в этих дампах ОТСУТСТВУЕТ

Проверено по всем артефактам сессии 11:57:

1. **Ни одного URL** `kys.linkvertise.lol / auth.getmadium.xyz / lootlabs / RTDL / VGuard / PGPSC / PGPG / pushToTalk / handshake` в `traffic.jsonl` и `events.log` (grep = 0 совпадений; событие `RG-ENDPOINT` не сработало ни разу).
2. **Ни одного SubtleCrypto-перехвата**: в `crypto.jsonl` только четыре вида записей —
   `getterAccess` (2357, все — YouTube player base.js трогает `window.crypto`),
   `sendBeacon` (232, `/qlog/add`, `/sync-metrics` — adtech-пиксели),
   `visibility` (223), `installed` (92). Нет `digest/sign/deriveBits/importKey/encrypt/decrypt`.
   То есть PoW/RTDL-крипто в этой сессии **не выполнялось вообще**.
3. **wasm-дампов нет** (`__WASM_DUMPS__` пуст — SquareVM не инстанцировалась).
4. Среди 435 скачанных скриптов RG-терминов не встречается (проверено побайтовым поиском по хэшированному содержимому; 0 файлов из js_dumps не повторяются — это entirely другие сайты).

То, что реально посещалось в этой сессии (по href из `installed` + доменам трафика):
`wyv.gg` (витрина, `api.shoppex.io` отдаёт **402**), редирект-цепочки рекламной сети
(`cdn.aucey.com` → `hai8g.com/4/8770264` → `zk1w.com`, `litenery.shop/detect.php`,
`winline.kz/x5/`), `youtube.com` (watch-страницы), FingerprintJS (`eu.api.fpjs.io`,
`fpjscdn.net/v4/PONBWM1tJvDjA52Jopft`), `my.rtmark.net`, `cdntechone.com/datatechonert.com`,
рекламный стек Google (doubleclick/googlesyndication), расширение браузера
`cimiefiiaegbelhefglklhhakcgmhkai` (page-script.js ×22). Это **ad-tech/affiliat-цепочка**,
а не объект исследования.

### Причина отсутствия RG-трафика — баг самого capture_attach.js (найдено при разборе)

Во всех записях `dir:"req"` поле `url` пустое, хотя в обработчике он читается из
деструктуризации события CDP. В текущем Chrome (155) `Network.requestWillBeSent` отдаёт URL
в `event.request.url`, а не в корне события. Следствия, видимые в дампе:

- имена файлов скриптов — `NNNN_undefined.js` (URL был `undefined`);
- фильтр `RG-ENDPOINT` никогда не срабатывал (тестировал пустую строку);
- `hosts` в статистике пустые у 1058 записей.

**Исправлено** (см. `scripts/capture_attach.js`): фолбэк `e.url || request.url`, расширен
регулярник RG-эндпоинтов (добавлены `VGuard|DTOM|TaskStarted|linkvertise|getmadium|lootlabs`),
файлы теперь именуются `NNNN_<host>_<path>.js`, wasm-ответы (магический номер `\0asm`)
складываются в `wasm/`, а JSON-ответы RG-эндпоинтов — дополнительно в `responses/`.

Для существующего дампа 11:57 URL восстановлены постфактум из записей `dir:"resp"`
(там `response.url` присутствует) — все 435 скриптов переименованы в
`NNNN_<домен>_<путь>.js`; сопоставление по id запроса точное.

## Что полезного всё-таки есть в новом дампе

1. **Подтверждение «шума» окружения**: в реальной пользовательской сессии hijacker ловит
   тысячи ложных `getterAccess crypto` от YouTube — при боевом прогоне цепочки RG такие
   стоки нужно фильтровать по src скрипта (уже можно: в стеке виден URL источника).
2. **FingerprintJS Pro** (`eu.api.fpjs.io/DwmA/JNZ1Dz7/7?q=PONBWM1tJvDjA52Jopft`) используется
   ad-цепочкой — если когда-нибудь RG сверяется с этим же fpjs-id, это вектор связности
   анти-фрод профилей. Пока прямых связей с RG не найдено.
3. Отрицательный результат важен: **следующий прогон должен вестись именно по цепочке**
   Madium → kys.linkvertise.lol → lootlabs, иначе crypto.jsonl снова будет бесполезен.

## Дальнейшие шаги (обновлённый план)

1. Перезаписать целевую сессию исправленным `capture_attach.js`:
   ```bash
   google-chrome-stable --remote-debugging-port=9222 \
     --disable-backgrounding-occluded-windows --disable-renderer-backgrounding \
     --disable-background-timer-throttling &
   node scripts/capture_attach.js
   # затем вручную: app.getmadium.xyz -> старт квеста -> kys.linkvertise.lol -> lootlabs
   ```
   Ожидаемые маркеры успеха: события `RG-ENDPOINT`, записи `digest` (PoW sha256),
   `deriveBits X25519` + `encrypt AES-GCM` (RTDL), файлы в `responses/*VGuard*.json`.
2. Прогнать `python3 analysis/captures_analyze.py` по новому live-дампу.
3. Если `deriveBits.secretB64` появится — расшифровать пакеты pushToTalk офлайн
   (AES-256-GCM, iv уже пишется в записи `encrypt`).

## Артефакты этого анализа

- Переименованные скрипты: `captures/attach_2026-10-14T11-57-01-853Z/scripts/NNNN_<host>_<path>.js` (435 шт.)
- Патч recorder'а: `scripts/capture_attach.js` (см. выше список изменений)
- Этот отчёт: `reports/ATTACH_2026-10-14_FINDINGS.md`
