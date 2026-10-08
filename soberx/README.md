# SoberX — Roblox на Linux с поддержкой кастомных APK

Полностью открытый аналог [sober](https://github.com/vinegarhq/sober) (vinegarhq), написанный с нуля.
Два режима запуска клиента:
1. **Windows-клиент через Wine/DXVK** (как у original Sober);
2. **Android-клиент из APK** — можно загружать *кастомные* .apk файлы Roblox,
   они валидируются, устанавливаются и запускаются через Waydroid/adb.

## Возможности
- Вход через браузер (flow `.ROBLOSECURITY`, как у sober), хранение токена в libsecret или файле 0600;
- Каналы версий: stable / canary / atchi / legacy_avi + автообновление клиента;
- GUI на GTK4/libadwaita (аналог sober_services) и полноценный CLI;
- Менеджер кастомных APK: проверка zip/AXML-манифеста, ABI, версии, извлечение `libroblox.so` и ассетов;
- Установка зависимостей Wine (winetricks vcrun2022, dxvk), запуск `RobloxPlayerBeta.exe`;
- Готовый Flatpak-манифест (`flatpak/org.soberx.Client.json`).

## Структура
```
soberx/
├── src/soberx/
│   ├── settings.py   # JSON-конфиг XDG + пути клиентов
│   ├── version.py    # версия/каналы Roblox (clientsettingscdn)
│   ├── download.py   # загрузки с прогрессом и SHA-256
│   ├── auth.py       # веб-вход, libsecret/файл-хранилище cookie
│   ├── apk.py        # парсинг/валидация/установка кастомных APK
│   ├── install.py    # Wine-префикс и Android(APK)-режимы, запуск
│   ├── cli.py        # soberx login|update|apk ...|launch
│   └── gui.py        # GTK4/adw окно с кнопками и списком APK
├── flatpak/org.soberx.Client.json
├── build-flatpak.sh
├── data/org.soberx.Client.desktop
├── tests/test_apk.py
└── pyproject.toml
```

## Быстрый старт (без установки)
```bash
PYTHONPATH=src python3 -m soberx.cli whoami
PYTHONPATH=src python3 -m soberx.cli channel canary
PYTHONPATH=src python3 -m soberx.cli update          # нужен wine
PYTHONPATH=src python3 -m soberx.cli apk check ~/my-roblox.apk
PYTHONPATH=src python3 -m soberx.cli apk install ~/my-roblox.apk
PYTHONPATH=src python3 -m soberx.cli launch --place 1234567890
```

## Установка
```bash
pipx install ./soberx            # или: pip install ./soberx[gui]
soberx-gui                       # графический режим
```

## Сборка Flatpak
Требуются `flatpak` и `flatpak-builder`:
```bash
./build-flatpak.sh
flatpak run org.soberx.Client
```
Примечание: для Wine-режима внутри sandbox Flatpak нужно расширить манифест
wine-рантаймом (org.winehq.Wine) — базовый манифест покрывает APK/CLI/GUI-часть.

## Тесты
```bash
python3 tests/test_apk.py     # 9/9 pass
```

## Юридическая заметка
Проект не аффилирован с Roblox Corporation. Использование кастомных APK
может нарушать ToS игры; клиентские файлы скачиваются с официальных CDN Roblox.

## Управление (убираем «бесячий тач»)

APK Roblox не поддерживает клавиатуру — в sober это решается запуском **x86-64**
сборки Windows-клиента (.exe, нативные WASD+мышь) через Wine. SoberX делает то же:

* **Wine-режим (`soberx update` + `soberx launch`)** — x86-64 .exe клиент, управление ПК-нативное, без тача вообще (рекомендуется);
* **APK-режим (`soberx launch --apk-mode`)** — если нужен именно APK (кастомная версия):
  * включите в GUI галку «Клавиатура/мышь вместо тач-управления» — при запуске поднимается scrcpy-окно (мышь→тач без свайп-гизмов);
  * профиль биндов WASD→виртуальный-стик: `soberx input list`, экспорт `soberx input profile --export controls.json`;
  * импорт готовых конфигов GameLoop/LDPlayer: `soberx input profile --import-gameloop game.xml`;
  * ручная эмуляция тапов в контейнер: `soberx input feed w space` (через adb sendevent).
