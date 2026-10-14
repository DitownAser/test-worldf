"""Получение версий и URL загрузчика Roblox (как upstream vinegarhq/sober)."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from .http import ProgressCb, http_get, http_get_json

VERSION_URL = "https://setup.rbxcdn.com/version"
CLIENT_URL = "https://clientsettingscdn.roblox.com/v2/client-version/WindowsAppLog"

# Все известные каналы клиента и их settings-URL
CHANNELS: dict[str, str] = {
    "stable": CLIENT_URL,
    "canary": "https://clientsettingscdn.roblox.com/v2/client-version/WindowsCanary",
    "atchi": "https://clientsettingscdn.roblox.com/v2/client-version/WindowsAtch1",
    "legacy_avi": "https://clientsettingscdn.roblox.com/v2/client-version/WindowsChannel-AVI",
}

_VERSION_RE = re.compile(r"^[a-z]-[0-9a-f]{7}$")


def current_version() -> str:
    """Актуальная версия клиента Roblox (строка вида r-xxxxxxx)."""
    try:
        return http_get_json(CLIENT_URL)["clientVersionUpload"]
    except Exception:
        v = http_get(VERSION_URL).decode().strip()
        if not _VERSION_RE.match(v):
            raise RuntimeError(f"некорректный ответ version: {v!r}")
        return v


def channel_version(channel: str) -> str:
    """Версия по каналу: stable | canary | atchi | legacy_avi."""
    try:
        url = CHANNELS[channel]
    except KeyError:
        raise ValueError(f"неизвестный канал: {channel}") from None
    return http_get_json(url)["clientVersionUpload"]


def bootstrapper_url(version: str) -> str:
    """URL оф. установщика Windows — источник DLL для Wine-префикса."""
    return f"https://setup.rbxcdn.com/{version}-RobloxInstall.exe"


def setup_base_url(version: str) -> str:
    return f"https://setup.rbxcdn.com/{version}"


# ---- чанки (точная схема sober: version + chunk-storage + qjs + dlls) ----

DEFAULT_CHUNK_STORAGE = "https://roblox-1eb8602b03ee7600c9b97d8aa07d1095content.content.invisioncloudstatic.com"
ANDROID_CHANNEL_URL = "https://clientsettingscdn.roblox.com/v2/client-version/AndroidPlatform"


def _chunk_storage_from_apk() -> str | None:
    """Вытащить URL чанк-хранилища из assets/Roblox/version официального Android-APK."""
    try:
        android_ver = http_get_json(ANDROID_CHANNEL_URL)["clientVersionUpload"]
        data = http_get(f"https://setup.rbxcdn.com/{android_ver}-roblox.apk", timeout=60)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.read("assets/Roblox/version").decode().splitlines()[1].strip()
    except Exception:
        return None


def chunk_storage_for(version: str, channel: str = "stable") -> str:
    """Получить URL чанк-хранилища из APK-версии (как делает sober через AndroidChannel),
    либо вернуть канонический CDN по умолчанию для wine-канала."""
    if channel in ("stable", "canary", "atchi"):
        # у Roblox единый content-CDN; берём его из публичного Android-канала
        storage = _chunk_storage_from_apk()
        if storage:
            return storage
    return DEFAULT_CHUNK_STORAGE


def chunks_base(version: str, storage: str) -> str:
    """Базовый URL чанков: <storage>/content/<version>/"""
    return f"{storage.rstrip('/')}/content/{version}/"


def get_qjs(version: str, storage: str, dest_dir: Path) -> Path:
    """Скачать securitychecks-qjs.js (нужен клиенту, как в sober)."""
    from .download import download
    url = f"{chunks_base(version, storage)}securitychecks.qjs.js"
    return download(url, Path(dest_dir) / "securitychecks.qjs.js")


# Файлы клиента, которые sober качает из чанков (список wine-дистрибуции)
CLIENT_CHUNKS = [
    "RobloxPlayerBeta.exe",
    "AppLaunch.dll",
    "Microsoft.WindowsAppRuntime.Bootstrap.dll",
    "c1.dll", "c2.dll", "c3.dll", "c4.dll", "c5.dll",
    "nativehtml_1.dll", "nativehtml_2.dll", "nativehtml_3.dll",
    "VideoDecodingExtensionManifest.xml",
    "rbxcrash-handler.exe", "data.prf",
]


def download_client_chunks(version: str, storage: str, dest_dir: Path,
                           progress: ProgressCb | None = None) -> list[str]:
    """Скачать все чанки клиента в versions/<version> (точная логика sober)."""
    from .download import download
    dest = Path(dest_dir)
    got = []
    for name in CLIENT_CHUNKS:
        try:
            download(chunks_base(version, storage) + name, dest / name, progress=progress)
            got.append(name)
        except Exception:
            # часть чанков может отсутствовать на старых версиях — пропускаем
            continue
    return got
