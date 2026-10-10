#!/usr/bin/env bash
# Сборка бинарника SoberX (Rust) для Arch Linux.
# Вариант 1 — локально (на Arch или любом Linux x86-64 с rustup):
set -euo pipefail
cd "$(dirname "$0")"

source "$HOME/.cargo/env" 2>/dev/null || true
cargo build --release
cargo test --release

BIN=target/release/soberx
echo "готово: $BIN ($(du -h "$BIN" | cut -f1))"

# Установка локально:
#   sudo install -Dm755 "$BIN" /usr/local/bin/soberx
# либо через makepkg (см. PKGBUILD в этом каталоге):
#   makepkg -si
