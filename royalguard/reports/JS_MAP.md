# Карта JS-артефактов: полная разборка и взаимосвязи

Дамп **двух независимых браузерных сессий**, сохранённых в файлы с расширением `.js`.
Всего 37 файлов (26 пронумерованных `00NN_*.js` + 11 `iframe_lootlabs_15_*.js`).
Из них **4 файла — это HTML-страницы**, а не JavaScript (0013, 0017, 0019, 0023).

---

## СЕССИЯ A — app.getmadium.xyz (Next.js/Turbopack) — файлы 0001–0012

| Файл | Размер | Что это |
|---|---|---|
| 0001 `_2284aac9` | 27 KB | Чанк Turbopack: React runtime (ошибки `react.dev/errors`) |
| 0002 `_cbc6ac25` | 191 KB | Чанк: vendor-библиотеки приложения |
| 0003 `_3e5bc7ca` | 32 KB | **Cloudflare Insights beacon** (`static.cloudflareinsights.com`) — аналитика RUM. Дубликат `iframe_lootlabs_15_3e5bc7ca.js` |
| 0004 `_aee2d073` | 3 KB | Чанк: Next.js internals (`DecodeError`, `WEB_VITALS`, `getURL`…) |
| 0005 `_a3ac200f` | 55 KB | Чанк: роутер/скролл (`onlyHashChange`, `documentElement`) |
| 0006 `_dfa58a0b` | 228 KB | Чанк: Next.js runtime + `NEXT_DEPLOYMENT_ID` |
| 0007 `_c98dd55b` | 45 KB | Чанк приложения |
| 0008 `_c7cb6ba5` | 25 KB | Чанк приложения |
| 0009 `_7c95ea25` | 11 KB | `turbopack-…` — загрузчик чанков Turbopack |
| 0010 `_a6615a6b` | 145 KB | Чанк: форматирование URL / next router |
| 0011 `_6598548d` | 2 KB | Маленький чанк-инлайнер |
| 0012 `_100d8545` | 145 KB | **Полный побайтовый дубликат 0010** (тот же хэш содержимого) |

**Взаимосвязь:** все 12 файлов загружаются одним HTML `app.getmadium.xyz`; 0009 является лоадером, который по манифесту подтягивает 0001–0010. Это легитимный фронтенд Next.js, к linkvertise-цепочке отношения не имеет (переход только по ссылке «madium» из lootlabs-задания). Cloudflare-beacon (0003) вставляется автоматически на обеих страницах — поэтому он встречается дважды.

---

## СЕССИЯ B — kys.linkvertise.lol → iframe lootlabs (основная цепочка)

### Порядок загрузки и граф зависимостей

```
[1] 0023_Z_f92f45df.js  = HTML страницы /VMc/VGuard_v1?TID=...&TAD=...   ← КУДА ПРИВОДИТ ОБХОД
     ├─ инлайн 0020 (window.o1=location.href + перехват console.error/warn, window.copyConsoleErrors)
     ├─ инлайн 0021 («Hashing process started!!!» — спам рандомными SHA-512 хэшами в консоль)
     └─ инлайн 0022 (LBS overlay: прогресс «loading», RL_KEY='lbs_rl', forensics-логи [LBS-F])
          ↓ внутри показывает lootlabs/linkvertise iframe:
[2] iframe_lootlabs_15_761049ab.js  document.session='C98bc158-…'        ← сессия лута
[3] iframe_lootlabs_15_829b6152.js  Hotjar loader (hjid:6705157)          ← запись поведения
    iframe_lootlabs_15_3742ed17.js  Hotjar runner (atob, beacon)
    iframe_lootlabs_15_6cf24eed/8041980a/8fda68ac/b396c684/b8a410aa/d5ca76af/f11741e0  — модули Hotjar/LootLabs
[4] iframe_lootlabs_15_a55b5413.js  ПАРАМЕТРЫ ЛАБИРИНТА:
        PUBLISHER_NAME="Olemad", PUBLISHER_TITLE="Just a moment - B.Y.P.A.S.S Protected"
        KEY=59095421728687321, PUBLISHER_ID=542185, TIER_ID=3, NUM_OF_TASKS=1, SHOW_UNLOCKER=true
[5] iframe_lootlabs_15_0a3e527c / b9258540 — доп. скрипты лабиринта
[6] iframe_lootlabs_15_4d96a090 (= 0026): `document.title+"\n"+document.body.innerText`
        ← ДАМП DOM В CONSOLE — это debug-мост между фреймами
```

### Параллельная ветка — страница DTOM (анти-адблок Red-Square)

```
[0] 0019 = HTML страницы /DTOM/<uuid> (B.Y.P.A.S.S · RED-SQUARE)
     └─ инлайн 0018 — ВЕСЬ ЛОГИЧЕСКИЙ КОД DTOM (см. ниже)
          ├─ NEEDS_CPT=false → proceed() → location.href = NEXT_HREF="/TaskStarted/<uuid>"
          ├─ HAS_ADS=true    → showContinue() (кнопка continue-box; здесь её нет — ADS_SCRIPT_URL=null)
          └─ reportAdblock() → POST /DTOM/<uuid>/adblock {d:0|1}  (только статистика!)
                    ↓ TaskStarted запускает ВМ:
[7] 0024_inline_script_05438659.js (440 KB) — VM-интерпретатор Square-VM/VGuard
     глобал: vmf_3d9168; 173 опкода; base64+XOR; НОЛЬ сетевых запросов
[8] 0025__a0d94da9….js — результат работы ВМ:
     location.replace("https://kys.linkvertise.lol/VMc/VGuard_v1?TID=035ca88c-…&TAD=<base64>")
                    ↓ и вот мы на шаге [1] (0023)
```

### Остальные файлы

| Файл | Что это | Связь |
|---|---|---|
| 0013 (HTML) | Шаблон страницы PoW «Site» | Используется для `/api/rg` challenge-страниц Royal-Guard |
| 0014 | JS той же PoW-страницы: тикеры «Blocking DDoS attacks», честный **SHA-256 proof-of-work** (`prefix:nonce`, сложность), сабмит формы, галка «I'm not a robot», HealthCheck `/api/rg/HealthCheck` | Реальная (единственная криптографическая) защита в цепочке |
| 0015 | page-script расширения браузера KDE Plasma Integration (`org.kde.pbi`, MediaSession/mpris) | Мусор дампа: прилетел от установленного у жертвы расширения, к сайту не относится |
| 0016 | `this.src='https://rip.linkvertise.lol/favicon.ico'` onerror-fallback | Обрывок favicon с битым доменом |
| 0017 (HTML) | Страница `404 Not Found \| Royal-Guard` | Ошибка сервера, попавшая в дамп |
| 0020 | Перехват консоли + копирование ошибок в буфер | Дебаг-инструмент автора защиты |
| 0021 | Вечный цикл `tick()` со случайными SHA-512 в консоль | Троллинг/шум для analysts |
| 0022 | LootLabs loading-overlay + anti-tamper MutationObserver | UI шага [1] |
| 0026 | дубль 4d96a090 (дамплер DOM) | мост fuzzer↔page |

---

## Ключевые наблюдения о связях

1. **Единый UUID задачи** `009b16ef-56de-47ea-873f-ddf90bf60269` присутствует в имени всех файлов 0013–0019, 0021–0025 — весь дамп снят с одной сессии DTOM→TaskStarted→VMc.
2. **Скрипт 0018 содержит бэкдор-признание** автора (`window.io20`) — обход через замену `DTOM`→`TaskStarted` + `&CA=crypto.randomUUID()`. Именно его реализует `bypass_antiblock_v2.user.js`.
3. **0024 (ВМ) ни с чем не связана сетью**: её вывод — единственный редирект 0025 с токеном TAD, который генерируется на клиенте и сервером не верифицируется.
4. **Hotjar hijid 6705157** подключён со стороны lootlabs-iframe (829b6152 → 3742ed17 → крупные модули d5ca76af/f11741e0) — полноценная запись сессии пользователя.
5. **Дубликаты**: 0003 ≡ iframe_3e5bc7ca (Cloudflare beacon), 0010 ≡ 0012 (чанк Next.js), 0026 ≡ iframe_4d96a090 (дамплер DOM).
6. Единственная реальная вычислительная защита — PoW в 0014 (Royal-Guard); всё остальное — косметика и телеметрия.

---

## Дополнение 2026-10-13: живой CDP-дамп `captures/`

Появилась новая папка `captures/` (logs/events.log, logs/traffic.jsonl, responses/, page_scripts_1/) —
рантайм-запись той же цепочки с полной сетевой последовательностью и консолью. Ключевые уточнения к карте:

- **Уточнение к наблюдению 3**: ВМ из 0024 в живом рантайме ДЕЛАЕТ сетевые запросы:
  `/api/rg/encrypt-tunnel/PGPG|PGPSC` (X25519+AES-256-GCM рукопожатие «Yates Exchange», цикл ~50–65 с),
  `/api/RTDL/v4/SquareVM` (байткод), `/api/rg/v2/enigma/RTDL/pushToTalk` ×22 (шифрованная телеметрия,
  heartbeat 15/60 с + события visibilitychange). Статический вывод «ноль сетевых запросов» верен только
  для самого файла 0024 — сеть инициируют подгружаемые модули RTDL/RGCS.
- **PoW подтверждён криптографически**: sha256(`prefix:nonce`) даёт 5 ведущих нулей при diff=4.5; решается за <1 с.
- Полный разбор протокола и флоу — в новом файле **`CAPTURES_FINDINGS.md`**.
