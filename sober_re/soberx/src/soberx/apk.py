"""Работа с кастомными APK Roblox: парсинг, валидация, установка, извлечение librogbox.so.

Поддержка двух форматов APK-источников (как у sober есть каналы):
  official  — скачивание с pubnub-канала Roblox Android
  custom    — любой .apk/.xapk файл, выбранный пользователем
"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .http import download_file, http_get_json

PUBNUB_CHANNEL = "https://pubnub.robxn.com/android"  # канал релизов Android-клиента

_ABI_RE = re.compile(r"lib/([a-zA-Z0-9_\-]+)/")
_CLIENT_LIB_RES = (
    re.compile(r"lib/[a-z0-9_\-]+/libroblox\.so$"),
    re.compile(r"lib/[a-z0-9_\-]+/librogbox\.so$"),
    re.compile(r"assets/[^/]+\.bundle$"),
)


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


def _abis_in(zf: zipfile.ZipFile) -> list[str]:
    """Список ABI-каталогов с нативными библиотеками в APK."""
    return sorted({m.group(1) for n in zf.namelist() if (m := _ABI_RE.match(n))})


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


def _has_client_artifacts(names: list[str]) -> bool:
    """Есть ли в архиве характерные для Roblox-клиента файлы."""
    return any(n.startswith("assets/ClientContent.xml") or n == "assets/ClientVersion.xml"
               or any(rx.match(n) for rx in _CLIENT_LIB_RES) for n in names)


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
            abis = _abis_in(zf)
            has_client = _has_client_artifacts(zf.namelist())
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
    j = http_get_json(PUBNUB_CHANNEL)
    url = j["url"] if isinstance(j, dict) else j[0]["url"]
    return download_file(url, dest_dir / f"official-{Path(url).name}", timeout=120)


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
        abis = [abi] if abi else _abis_in(zf)
        for a in abis:
            prefix = f"lib/{a}/"
            for n in zf.namelist():
                if n.startswith(prefix) and n.endswith(".so"):
                    tgt = dest / a / Path(n).name
                    tgt.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(n) as src, open(tgt, "wb") as f:
                        shutil.copyfileobj(src, f)
                    out.append(tgt)
    return out


def installed_list(store_dir: Path) -> list[ApkInfo]:
    """Инспекция всех APK в хранилище SoberX."""
    return [inspect_apk(p) for p in sorted(store_dir.glob("*.apk"))]


def run_on_emulator(apk: Path, serial: str | None = None) -> subprocess.CompletedProcess:
    """Установить APK на запущенный Android-эмулятор через adb (если доступен)."""
    cmd = ["adb"] + (["-s", serial] if serial else []) + ["install", "-r", str(apk)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)
