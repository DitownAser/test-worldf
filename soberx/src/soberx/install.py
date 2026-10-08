"""Установка клиента Roblox: Windows-вариант через Wine и Android-вариант из APK."""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable

from . import version as ver
from .download import download
from .settings import Settings

Progress = Callable[[str, int, int], None]  # (этап, текущий, всего)


def have(cmdname: str) -> bool:
    return shutil.which(cmdname) is not None


class Installer:
    def __init__(self, st: Settings, on_progress: Progress | None = None):
        self.st = st
        self.cb = on_progress or (lambda *_: None)

    # ---------- Windows/Wine ----------
    def install_wine(self) -> Path:
        """Создаёт префикс, ставит winetricks-зависимости и скачивает клиент."""
        if not have("wine"):
            raise RuntimeError("wine не найден в PATH — установите wine (>=9)")
        prefix = self.st.prefix_dir
        v = ver.channel_version(self.st.channel)
        self.cb("версия", 0, 100)
        env = {"WINEPREFIX": str(prefix), "WINEDEBUG": "-all"}
        subprocess.run(["wineboot", "--init"], env={**__import__("os").environ, **env},
                       check=True, timeout=600)
        self.cb("dll", 30, 100)
        for dep in ("vcrun2022", "dxvk"):
            if have("winetricks"):
                subprocess.run(["winetricks", "-q", dep],
                               env={**__import__("os").environ, **env}, timeout=1800)
        self.cb("загрузка клиента", 50, 100)
        base = ver.setup_base_url(v)
        dst = self.st.versions_dir / v
        for name in ("RobloxPlayerBeta.exe", "InstallUtils.dll", "ClientSettings.xml"):
            try:
                download(f"{base}/{name}", dst / name,
                         progress=lambda a, b, n=name: self.cb(f"{n} {a}/{b}", a, b))
            except Exception as e:
                print(f"пропуск {name}: {e}")
        self.st.last_version = v
        self.st.save()
        self.cb("готово", 100, 100)
        return dst

    # ---------- Android/APK ----------
    def install_apk(self, apk_path: Path | None = None) -> Path:
        """Устанавливает кастомный (или официальный) APK как источник клиента.

        Извлекает нативные библиотеки и ассеты в versions/<apk-version>,
        сохраняет путь в настройках (apk_source=custom).
        """
        from . import apk as apkmod
        store = self.st.apk_store_dir
        if apk_path is None:
            self.cb("официальный APK", 0, 100)
            apk_file = apkmod.download_official(store)
        else:
            self.cb("валидация APK", 0, 100)
            apk_file = apkmod.install_apk(Path(apk_path), store)
        info = apkmod.inspect_apk(apk_file)
        vtag = info.version_name or apk_file.stem
        dst = self.st.versions_dir / f"android-{vtag}"
        self.cb("извлечение библиотек", 40, 100)
        abi = "arm64-v8a" if "arm64-v8a" in info.abi else (info.abi[0] if info.abi else None)
        libs = apkmod.extract_native_libs(apk_file, dst / "lib", abi)
        with zipfile.ZipFile(apk_file) as zf:
            (dst / "assets").mkdir(parents=True, exist_ok=True)
            for n in zf.namelist():
                if n.startswith("assets/") and Path(n).suffix in (".xml", ".bundle", ".json"):
                    target = dst / n
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(n) as s, open(target, "wb") as f:
                        shutil.copyfileobj(s, f)
        self.st.custom_apk_path = str(apk_file)
        self.st.apk_source = "custom" if apk_path else "official"
        self.st.last_version = vtag
        self.st.save()
        self.cb("готово", 100, 100)
        return dst

    # ---------- запуск ----------
    def launch(self, place: str | None = None) -> subprocess.Popen:
        """Запускает установленный клиент (Windows через wine или эмулятор с APK)."""
        token = self.st.username
        if self.st.apk_source == "custom" or self.st.apk_source == "official":
            # вариант Android: запускаем эмулятор и ставим APK (нужен android emulator/weyback)
            emu = "waydroid" if have("waydroid") else ("scrcpy" if have("adb") else None)
            if emu == "waydroid":
                cmd = ["waydroid", "app", "start", "com.roblox.client"]
                if place:
                    cmd += ["--placeId", place]
                return subprocess.Popen(cmd)
            raise RuntimeError("не найден waydroid/adb — установите waydroid для APK-режима")
        v = self.st.last_version
        exe = self.st.versions_dir / v / "RobloxPlayerBeta.exe"
        if not exe.is_file():
            raise RuntimeError("клиент не установлен — нажмите «Обновить»")
        env = {"WINEPREFIX": str(self.st.prefix_dir)}
        args = [str(exe)]
        if token:
            args.append(f"-t{token}")
        if place:
            args.append(f"-a{place}")
        import os
        return subprocess.Popen(["wine"] + args, env={**os.environ, **env})
