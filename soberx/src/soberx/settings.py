"""Хранилище настроек SoberX (JSON в XDG-конфиге)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path


def xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


@dataclass
class Settings:
    # общие
    username: str = ""            # имя пользователя Roblox (для пути клиента)
    channel: str = "stable"       # stable | canary | atchi | legacy_avi
    discord_rpc: bool = True
    browser: str = "xdg-open"     # команда открытия ссылок авторизации
    # графика/клиент
    gpu: str = "auto"             # auto | intel | nvidia | amd
    use_winewayland: bool = False
    fullscreen: bool = False
    custom_fps: int = 0           # 0 = по умолчанию движка
    oodle_disabled: bool = False
    xmllog_enabled: bool = False
    # кастомные APK
    apk_source: str = "official"  # official | custom
    custom_apk_path: str = ""     # путь к загруженному .apk
    # управление в APK-режиме
    input_mode: str = ""          # "" (wine) | "apk-mapping" (клавиатура->тапы)
    control_profile: str = ""     # путь к controls.json, пусто = профиль по умолчанию
    # прочее
    last_version: str = ""

    def __post_init__(self):
        self._dir = xdg_config_home() / "soberx"
        self._file = self._dir / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            data = json.loads(s._file.read_text())
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, v)
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            # битый конфиг — начинаем с чистого, оригинал сохраняем
            try:
                s._file.rename(s._file.with_suffix(".json.bak"))
            except OSError:
                pass
        return s

    def save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(self._file)

    # --- производные пути (как у sober: ~/.sober/<user>/...) ---
    @property
    def data_dir(self) -> Path:
        return xdg_data_home() / "soberx"

    @property
    def client_root(self) -> Path:
        user = self.username or "default"
        return self.data_dir / "clients" / user

    @property
    def versions_dir(self) -> Path:
        return self.client_root / "versions"

    @property
    def prefix_dir(self) -> Path:
        """Wine-префикс (или корень эмуляции Android-варианта)."""
        return self.client_root / "prefix"

    @property
    def apk_store_dir(self) -> Path:
        return self.data_dir / "apks"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "logs" / "client.log"
