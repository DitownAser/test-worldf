"""Получение версий и URL загрузчика Roblox (как upstream vinegarhq/sober)."""
from __future__ import annotations

import json
import re
import urllib.request

VERSION_URL = "https://setup.rbxcdn.com/version"
CLIENT_URL = "https://clientsettingscdn.roblox.com/v2/client-version/WindowsAppLog"


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SoberX/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def current_version() -> str:
    """Актуальная версия клиента Roblox (строка вида r-xxxxxxx)."""
    try:
        data = http_get(CLIENT_URL).decode()
        j = json.loads(data)
        return j["clientVersionUpload"]
    except Exception:
        v = http_get(VERSION_URL).decode().strip()
        if not re.match(r"^[a-z]-[0-9a-f]{7}$", v):
            raise RuntimeError(f"некорректный ответ version: {v!r}")
        return v


def channel_version(channel: str) -> str:
    """Версия по каналу: stable | canary | atchi | legacy_avi."""
    chans = {
        "stable": CLIENT_URL,
        "canary": "https://clientsettingscdn.roblox.com/v2/client-version/WindowsCanary",
        "atchi": "https://clientsettingscdn.roblox.com/v2/client-version/WindowsAtch1",
        "legacy_avi": "https://clientsettingscdn.roblox.com/v2/client-version/WindowsChannel-AVI",
    }
    if channel not in chans:
        raise ValueError(f"неизвестный канал: {channel}")
    j = json.loads(http_get(chans[channel]).decode())
    return j["clientVersionUpload"]


def bootstrapper_url(version: str) -> str:
    """URL оф. установщика Windows — источник DLL для Wine-префикса."""
    return f"https://setup.rbxcdn.com/{version}-RobloxInstall.exe"


def setup_base_url(version: str) -> str:
    return f"https://setup.rbxcdn.com/{version}"
