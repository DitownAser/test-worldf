"""Игровой цикл точь-в-точь как sober (vinegarhq):

1. читаем/скачиваем version-файл канала;
2. скачиваем чанки клиента (RobloxPlayerBeta.exe + DLL) и qjs;
3. ставим winetricks-зависимости в префикс;
4. открываем браузерную ссылку авторизации, ловим redirect на
   http://localhost:59251/auth?ROBLOSECURITY=... (webview-сервер как у sober);
5. запускаем wine RobloxPlayerBeta.exe с токеном (-t).

Отличия от sober: свой открытый код на Python вместо Rust-лоадера;
libredirect собирается на месте; кастомные APK — отдельный модуль apk.py.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse, parse_qs, unquote

from . import version as ver
from .download import download
from .libredirect import ensure_libredirect
from .settings import Settings
from .versionfile import VersionFile, read_version, write_version

AUTH_PORT = 59251  # тот же порт обратного вызова, что у официального клиента


class _AuthHandler(BaseHTTPRequestHandler):
    token_holder: dict = {}

    def do_GET(self):  # noqa: N802
        q = parse_qs(urlparse(self.path).query)
        tok = unquote((q.get("ROBLOSECURITY") or [""])[0])
        if self.path.startswith("/auth") and tok:
            _AuthHandler.token_holder["token"] = tok
            self.send_response(200)
            self.end_headers()
            self.wfile.write("<h2>SoberX: вход выполнен, можно закрыть окно.</h2>".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):  # тихо
        pass


def wait_for_token(timeout: int = 300) -> str | None:
    """Поднять localhost:59251 и дождаться ROBLOSECURITY из редиректа браузера."""
    srv = HTTPServer(("127.0.0.1", AUTH_PORT), _AuthHandler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        end = time.time() + timeout
        while time.time() < end:
            tok = _AuthHandler.token_holder.get("token")
            if tok:
                return tok
            time.sleep(0.2)
        return None
    finally:
        srv.shutdown()
        srv.server_close()


class WineClient:
    """Полный аналог цикла sober для Windows-клиента под Wine."""

    def __init__(self, st: Settings, on_progress: Callable[[str], None] | None = None):
        self.st = st
        self.log = on_progress or (lambda s: None)

    # ---------- версия / чанки ----------
    def update(self) -> Path:
        v = ver.channel_version(self.st.channel)
        self.log(f"версия канала {self.st.channel}: {v}")
        vf = read_version(self.st.settings_dir, self.st.channel)
        storage = (vf.chunk_storage if vf else ver.chunk_storage_for(v, self.st.channel))
        dst = self.st.versions_dir / v
        got = ver.download_client_chunks(v, storage, dst,
                                         progress=lambda a, b: None)
        if "RobloxPlayerBeta.exe" not in got:
            # fallback: прямой URL установочного CDN (как делал старый install_wine)
            base = ver.setup_base_url(v)
            download(f"{base}/RobloxPlayerBeta.exe", dst / "RobloxPlayerBeta.exe")
        try:
            ver.get_qjs(v, storage, dst)
        except Exception as e:
            self.log(f"qjs пропущен: {e}")
        write_version(self.st.settings_dir,
                      VersionFile(channel_version=v, chunk_storage=storage),
                      self.st.channel)
        self.st.last_version = v
        self.st.save()
        self._ensure_prefix()
        self.log("клиент обновлён")
        return dst

    # ---------- wine-префикс ----------
    def _ensure_prefix(self):
        prefix = self.st.prefix_dir
        prefix.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "WINEPREFIX": str(prefix), "WINEDEBUG": "-all"}
        if not have("wine"):
            raise RuntimeError("wine не найден — установите wine (>=9)")
        done_marker = prefix / ".soberx-booted"
        if not done_marker.is_file():
            self.log("wineboot --init")
            subprocess.run(["wineboot", "--init"], env=env, check=True, timeout=600)
            for dep in ("vcrun2022", "dxvk", "corefonts"):
                if have("winetricks"):
                    self.log(f"winetricks {dep}")
                    subprocess.run(["winetricks", "-q", dep], env=env, timeout=1800)
            done_marker.touch()

    # ---------- авторизация через redirect-сервер (как webview у sober) ----------
    def login(self) -> str:
        url = ("https://www.roblox.com/login?mode=redirect&signIn=true"
               f"&source=Desktop&redirect_uri=http://localhost:{AUTH_PORT}/auth")
        browser = self.st.browser or "xdg-open"
        self.log(f"открой в браузере: {url}")
        try:
            subprocess.Popen([browser, url])
        except OSError:
            print("откройте ссылку вручную:", url)
        tok = wait_for_token()
        if not tok:
            raise RuntimeError("не получили токен за 5 минут")
        self.st.username = username_from_token(tok) or self.st.username
        self.st.token = tok
        self.st.save()
        self.log("вход выполнен")
        return tok

    # ---------- запуск игры ----------
    def launch(self, place: str | None = None) -> subprocess.Popen:
        v = self.st.last_version
        exe = self.st.versions_dir / v / "RobloxPlayerBeta.exe"
        if not exe.is_file():
            raise RuntimeError("клиент не установлен — выполните обновление")
        env = {**os.environ, "WINEPREFIX": str(self.st.prefix_dir)}
        # libredirect через LD_PRELOAD — точный механизм sober против блокировок
        so = ensure_libredirect(self.st.data_dir / "libredirect")
        if so:
            env["LD_PRELOAD"] = f"{so}:{env.get('LD_PRELOAD', '')}".rstrip(":")
        args = [str(exe)]
        if self.st.token:
            args.append(f"-t{self.st.token}")
        if place:
            args.append(f"-a{place}")
        if self.st.fullscreen:
            args.append("-f")
        if self.st.custom_fps:
            args.append(f"--fps={self.st.custom_fps}")
        if self.st.use_winewayland:
            args.append("--renderer=D3D11")
        self.log("запуск: wine " + " ".join(a[:6] + "***" if a.startswith("-t") else a for a in args))
        return subprocess.Popen(["wine"] + args, env=env)


def username_from_token(token: str) -> str | None:
    """best-effort: имя пользователя по .ROBLOSECURITY через auth sync endpoint"""
    try:
        import json, urllib.request
        req = urllib.request.Request(
            "https://apis.roproxy.com/auth/v2/usernamesync",
            headers={"Cookie": f".ROBLOSECURITY={token}", "User-Agent": "SoberX/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
            return j.get("userName") or j.get("username")
    except Exception:
        return None


def have(cmdname: str) -> bool:
    return shutil.which(cmdname) is not None
