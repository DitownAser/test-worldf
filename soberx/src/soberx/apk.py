"""Работа с кастомными APK Roblox: парсинг, валидация, установка, извлечение librogbox.so.

Поддержка двух форматов APK-источников (как у sober есть каналы):
  official  — скачивание с pubnub-канала Roblox Android
  custom    — любой .apk/.xapk файл, выбранный пользователем
"""
from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

PUBNUB_CHANNEL = "https://pubnub.robxn.com/android"  # канал релизов Android-клиента


@dataclass
class ApkInfo:
    path: Path
    package: str
    version_name: str
    version_code: int
    abi: list[str]
    size: int
    valid: bool
    error: str = ""


def _strings_from_axml(raw: bytes) -> list[str]:
    """Извлекает строки из бинарного AndroidManifest.xml (AXML).

    Пул строк AXML — это CJK/UTF-16 записи; дополнительно сканируем ASCII,
    чтобы ловить имена пакетов в упрощённых/битых файлах.
    """
    out: set[str] = set()
    # UTF-16LE последовательности длиной >= 2 символа
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){2,}", raw):
        out.add(m.group().decode("utf-16-le"))
    # ASCII токены (для тестовых/плоских манифестов)
    for m in re.finditer(rb"[\x20-\x7e]{3,}", raw):
        out.add(m.group().decode())
    return sorted(out)


def _read_android_manifest(zf: zipfile.ZipFile) -> tuple[str, str, int]:
    """Парсим AXML: package, versionName, versionCode."""
    try:
        raw = zf.read("AndroidManifest.xml")
    except KeyError:
        return "", "", 0
    strings = _strings_from_axml(raw)
    text = "\n".join(strings)
    pm = re.search(r"\b(com\.roblox\.[\w.]+|org\.vinegarhq\.[\w.]+|[\w]+\.[\w.]+)\b", text)
    pkg = pm.group(1) if pm else ""
    ver = ""
    code = 0
    vm = re.search(r"\d{1,4}\.\d{1,4}\.(\d{7,9})\.\d+", text)  # 1.6.9999999.1934
    if vm:
        ver = vm.group(0)
        code = int(vm.group(1))
    return pkg, ver, code


def inspect_apk(path: Path) -> ApkInfo:
    """Полная инспекция APK без внешних инструментов."""
    p = Path(path)
    if not p.is_file():
        return ApkInfo(p, "", "", 0, [], 0, False, "файл не найден")
    size = p.stat().st_size
    if not zipfile.is_zipfile(p):
        return ApkInfo(p, "", "", 0, [], size, False, "не является zip/APK")
    try:
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            abis = sorted({m.group(1) for n in names
                           for m in [re.match(r"lib/([a-zA-Z0-9_\-]+)/", n)] if m})
            has_client = any(n.startswith("assets/ClientContent.xml") or
                             n == "assets/ClientVersion.xml" or
                             re.match(r"lib/[a-z0-9_\-]+/libroblox.so$", n) or
                             re.match(r"lib/[a-z0-9_\-]+/librogbox.so$", n) or
                             re.match(r"assets/[^/]+\.bundle$", n) for n in names)
            pkg, ver, code = _read_android_manifest(zf)
    except (zipfile.BadZipFile, OSError) as e:
        return ApkInfo(p, "", "", 0, [], size, False, f"битый архив: {e}")
    # Roblox-APK: имя пакета содержит roblox ИЛИ внутри есть клиентские артефакты
    is_roblox = "roblox" in pkg.lower() or has_client
    err = "" if is_roblox else "похоже, это не Roblox APK (нет пакетов/ассетов Roblox)"
    return ApkInfo(p, pkg, ver, code, abis, size, valid=is_roblox, error=err)


def download_official(dest_dir: Path) -> Path:
    """Скачать официальный Android-APK по последнему номеру версии с канала."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    j = json.loads(urllib.request.urlopen(PUBNUB_CHANNEL, timeout=30).read())
    url = j["url"] if isinstance(j, dict) else j[0]["url"]
    out = dest_dir / f"official-{Path(url).name}"
    req = urllib.request.Request(url, headers={"User-Agent": "SoberX/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    return out


def install_apk(apk: Path, store_dir: Path) -> Path:
    """Валидирует и кладёт APK в хранилище SoberX (копия с именем версии)."""
    info = inspect_apk(apk)
    if not info.valid:
        raise ValueError(info.error or "APK не прошёл проверку")
    store_dir.mkdir(parents=True, exist_ok=True)
    name = f"{info.package or 'custom'}_{info.version_name or 'v0'}.apk"
    dst = store_dir / name
    shutil.copy2(apk, dst)
    return dst


def extract_native_libs(apk: Path, dest: Path, abi: str | None = None) -> list[Path]:
    """Извлекает нативные библиотеки (.so) нужной ABI из APK."""
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(apk) as zf:
        abis = [abi] if abi else sorted({m.group(1)
                for n in zf.namelist()
                for m in [re.match(r"lib/([a-zA-Z0-9_\-]+)/", n)] if m})
        for a in abis:
            for n in zf.namelist():
                if n.startswith(f"lib/{a}/") and n.endswith(".so"):
                    tgt = dest / a / Path(n).name
                    tgt.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(n) as src, open(tgt, "wb") as f:
                        shutil.copyfileobj(src, f)
                    out.append(tgt)
    return out


def installed_list(store_dir: Path) -> list[ApkInfo]:
    res = []
    for p in sorted(store_dir.glob("*.apk")):
        res.append(inspect_apk(p))
    return res


def run_on_emulator(apk: Path, serial: str | None = None) -> subprocess.CompletedProcess:
    """Установить APK на запущенный Android-эмулятор через adb (если доступен)."""
    cmd = ["adb"] + (["-s", serial] if serial else []) + ["install", "-r", str(apk)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)
