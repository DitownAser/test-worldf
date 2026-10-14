# Реверс-инжиниринг: две исследовательские ветки

Рабочая область разделена на два самостоятельных проекта (структурировано 2026-10-14):

## royalguard/ — анти-блок цепочки Madium → Royal Guard (kys.linkvertise.lol) → LootLabs
Точка входа: **`royalguard/README.md`** (хронология, выводы, структура, инструменты).
- `reports/` — все отчёты (JS_MAP, CAPTURES_FINDINGS, RESEARCH_REPORT, BYPASS_README)
- `js_dumps/` — 37 дампов скриптов двух сессий + iframe LootLabs
- `captures/` — живой CDP-дамп 2026-10-13 (трафик, консоль, ответы API)
- `scripts/` — запись сессий и перехват криптографии (capture_session.js — «запустил и всё пишет»)
- `analysis/` — Python-анализаторы; `bypass/` — userscripts обхода

## sober_re/ — бинарники Roblox-клиента Sober и libloader.so
- `binaries/` — sober, sober_services, libloader.so, libbadcpu.so, libmimalloc.so
- `out/` — артефакты ELF-анализа (elfutil.py, findings_*, payload_scan*, strings)
- `soberx/`, `soberx-rs/` — upstream-исходники клиента (Python и Rust)
- Отчёт по этой ветке: `royalguard/reports/RESEARCH_REPORT.md` (раздел про libloader)

Связь веток: Sober/libloader — нативный клиент, через который также запускается
цепочка квестов; JS-защита Royal Guard живёт в браузерной части (webview).
