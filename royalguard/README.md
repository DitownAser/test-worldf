# Royal Guard / Madium / LootLabs — исследование анти-блока цепочки квестов

Хронология и итоги всего исследования. Дата последнего обновления: **2026-10-14**.

## Цели и объект

Цепочка «Madium → kys.linkvertise.lol (Royal Guard) → lootlabs» защищает переход
по рекламным ссылкам. Задачи исследования:
1. Понять, как устроена защита (клиентская часть).
2. Найти слабые места и способы обхода.
3. Собрать инструменты для записи живых сессий и последующего реверса.

## Хронология работ

| Этап | Дата | Что делалось | Артефакты |
|---|---|---|---|
| 1. Статика JS | до 2026-10-13 | Разбор 37 дампов скриптов двух браузерных сессий + iframe LootLabs. Составлена карта: кто есть кто (Cloudflare beacon, Turbopack-чанки Madium, Royal-Guard загрузчик, inline-ВМ 0024, модули RGCS/RTDL). | `reports/JS_MAP.md`, `js_dumps/` |
| 2. Бинарники Sober | 2026-10-08 | ELF-анализ 5 объектов Roblox-клиента (sober, libloader.so и др.) — отдельная ветка исследования, см. `../sober_re/` | `../sober_re/` |
| 3. Живой CDP-дамп | 2026-10-13 | Полный сетевой лог сессии (94 запроса), консоль рантайма, PoW-верификация, декомпиляция логики антиадблока, открытие протокола RTDL. | `captures/`, `reports/CAPTURES_FINDINGS.md`, `analysis/captures_analyze.py` |
| 4. Инструменты перехвата | 2026-10-13…14 | `crypto_hijack.js` (перехват SubtleCrypto/WASM/fetch в рантайме), `hijack_attach.js`, `frida_dump.js`, и автономный `capture_session.js` (запустил — и всё пишется само). | `scripts/` |
| 5. Bypass-эксперименты | ранее | Userjs-скрипты обхода анти-блока v1/v2. | `bypass/` |
| 6. Структурирование | 2026-10-14 | Всё разложено по папкам (этот README — точка входа). | — |

## Ключевые выводы (кратко)

1. **Флоу подтверждён целиком**: `auth.getmadium.xyz/getkey/lootlabs/start` → DTOM
   (антиадблок + PoW) → TaskStarted → SquareVM → `/VMc/VGuard_v1?TID&...&TAD=...` →
   lootlabs-iframe → `links.lootlabs.gg/s`. Прохождение штатно ~5 сек.
2. **PoW Royal-Guard тривиален**: sha256("prefix:nonce") при diff≈4.5 решается
   перебором за <1 сек (~250k хешей). Верифицировано криптографически на реальном POST.
3. **RTDL («Yates Exchange»)** — зашифрованный телеметрический канал: ECDH X25519 +
   AES-256-GCM, heartbeat каждые 15/60 с, события visibilitychange, слепок окружения
   (3545 байт при старте). Минусы: нет forward secrecy (параметры handshake в URL),
   предсказуемый профиль пакетов, самодекларация anti-tamper, fail-open при ошибке
   handshake (`RTDL handshake unresolved [0x31]`).
4. **Антиадблок Red-Square**: 3 проверки (DOM-селекторы, fetch-пробы 8 CDN, pixel-probe),
   детект ложный в чистом браузере; обходится заглушками (см. `bypass/`).
5. **SquareVM (inline 0024, 439 КБ байткода)** сама не сетевая; сеть делают
   подгружаемые модули RGCS/RTDL. Байткод/ключи из офлайн-дампов НЕ извлекаются —
   нужен рантайм-перехват (`scripts/capture_session.js` + `scripts/crypto_hijack.js`).
6. **Практический итог для автоматизации**: сервер проверяет в основном корректность
   PoW и наличие RTDL-телеметрии; TAD — клиентский неверифицируемый параметр.
   Полноценный bypass требует эмуляции генерации `xn/hmac/payload2` (реверс ВМ) либо
   «подслушивания» примитивов в реальном браузере.

## Структура папки

```
royalguard/
├── README.md               ← этот файл
├── reports/                ← все отчёты (точка входа в чтение)
│   ├── RESEARCH_REPORT.md      общий отчёт (бинарники + контекст)
│   ├── JS_MAP.md               карта всех JS-дампов (сессии A/B + iframe)
│   ├── CAPTURES_FINDINGS.md    разбор живого CDP-дампа 2026-10-13 (главный документ)
│   └── BYPASS_README.txt       заметки по обходу
├── js_dumps/               ← исходные .js-дампы страниц (были в корне репозитория)
│   ├── session_a_getmadium/    файлы 0001–0012: приложение Madium (Next.js)
│   ├── session_b_kys/          файлы 0013–0026: Royal Guard (вкл. 0024 — inline-ВМ)
│   └── iframe_lootlabs/        11 файлов бандлов LootLabs iframe
├── captures/               ← живой CDP-дамп сессии 2026-10-13
│   ├── logs/{events.log, traffic.jsonl}
│   ├── responses/            JSON-ответы API Madium
│   ├── page_scripts_1/       снимок страницы (Next.js Flight)
│   └── manifest.json         манифест дампа
│   (live_<дата>/            ← сюда пишет capture_session.js новые дампы)
├── scripts/                ← инструменты записи/перехвата
│   ├── capture_session.js        АВТОНОМНЫЙ: сам стартует Chrome, пишет трафик+логи+крипто
│   ├── crypto_hijack.js          init-script: перехват SubtleCrypto/WASM/fetch
│   ├── hijack_attach.js          подключение hijack к уже запущенному Chrome
│   └── frida_dump.js             вариант через Frida
├── analysis/               ← скрипты анализа дампов и бинарей (Python)
│   ├── captures_analyze.py       воспроизводит все цифры из CAPTURES_FINDINGS.md
│   ├── an_vm*.py, vm_*.py        анализ ВМ/байткода
│   └── findings_*.txt, *_scan.txt, strings_loader.txt   промежуточные результаты
├── bypass/                 ← userscripts обхода анти-блока (v1, v2)
└── data/                   ← пусто; резерв под будущие датасеты (wasm-дампы, ключи)
```

## Как записать новую сессию (один comando)

```bash
cd royalguard/scripts
npm i chrome-remote-interface          # один раз
node capture_session.js "https://kys.linkvertise.lol/<TID>?..." 120
```

Скрипт сам:
- запустит Chrome с временным профилем. На Linux автопоиск покрывает
  `google-chrome-stable`, `google-chrome`, `/opt/google/chrome/chrome`, chromium,
  snap/flatpak, brave, edge; если у вас нестандартный путь — `CHROME_BIN=/путь node capture_session.js ...`;
- внедрит `crypto_hijack.js` ДО загрузки страницы;
- откроет URL и 120 с пишет всё в `royalguard/captures/live_<дата>/`:
  `traffic.jsonl`, `events.log`, `crypto.jsonl` (ключи/plaintext RTDL), `scripts/` (исходники).

Дальше анализ: `python3 analysis/captures_analyze.py` (пути к live-дампу — см. шапку файла).

## Связанные проекты

- `../sober_re/` — исследование бинарников Roblox-клиента Sober (libloader.so и т.д.),
  включая upstream-исходники `soberx/` и `soberx-rs/` и все артефакты ELF-анализа.
