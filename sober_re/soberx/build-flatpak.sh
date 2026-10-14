#!/usr/bin/env bash
# Сборка Flatpak SoberX. Требует: flatpak, flatpak-builder.
set -euo pipefail
cd "$(dirname "$0")"
flatpak-builder --user --install --force-clean build-dir flatpak/org.soberx.Client.json
echo "Готово. Запуск: flatpak run org.soberx.Client"
