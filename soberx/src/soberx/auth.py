"""Авторизация Roblox через веб-вход (flow как у sober: WebView/browser + cookie).

Результат — .ROBLOSECURITY cookie, сохраняемая в libsecret (если доступен)
или в файл с правами 0600.
"""
from __future__ import annotations

import json
import secrets
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

AUTH_BASE = "https://auth.roblox.com"
CSRF_URL = f"{AUTH_BASE}/v2/logout"
POLL_URL = f"{AUTH_BASE}/v2/authentication/login/check"
CREATE_URL = f"{AUTH_BASE}/v2/authentication/login/create"

OnStatus = Callable[[str], None]       # текстовый статус
OnUrl = Callable[[str], None]          # ссылка для открытия в браузере


class AuthManager:
    def __init__(self, settings_path: Path):
        self._cookie_file = settings_path / "authinfo.json"
        self._token: str | None = None
        self._csrf: str | None = None

    # ---------- хранение ----------
    def saved_cookie(self) -> str | None:
        """Читаем сохранённый токен: сначала libsecret, затем файл."""
        try:
            out = subprocess.run(
                ["secret-tool", "lookup", "service", "soberx", "account", "roblox"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        try:
            return json.loads(self._cookie_file.read_text())["token"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            return None

    def store_cookie(self, token: str) -> None:
        try:
            p = subprocess.run(["secret-tool", "store", "--label=SoberX Roblox",
                                "service", "soberx", "account", "roblox"],
                               input=token.encode(), capture_output=True, timeout=10)
            if p.returncode == 0:
                self._cookie_file.unlink(missing_ok=True)
                self._token = token
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        self._cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self._cookie_file.write_text(json.dumps({"token": token}))
        self._cookie_file.chmod(0o600)
        self._token = token

    def logout(self) -> None:
        self._token = None
        self._cookie_file.unlink(missing_ok=True)
        try:
            subprocess.run(["secret-tool", "clear", "service", "soberx"],
                           capture_output=True, timeout=5)
        except FileNotFoundError:
            pass

    # ---------- web flow ----------
    def _req(self, url: str, data: bytes | None = None, method: str = "POST"):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"User-Agent": "SoberX/1.0",
                                              "Content-Type": "application/json"})
        if self._csrf:
            req.add_header("x-csrf-token", self._csrf)
        return urllib.request.urlopen(req, timeout=30)

    def _refresh_csrf(self) -> None:
        try:
            r = self._req(CSRF_URL, b"{}", "POST")
            self._csrf = r.headers.get("x-csrf-token")
        except Exception:
            self._csrf = None

    def login_interactive(self, browser_cmd: str, on_status: OnStatus,
                          on_url: OnUrl) -> str:
        """Веб-вход без пароля в UI: создаём deep-link и ждём подтверждения.

        Аналогично sober: пользователь открывает ссылку в браузере,
        логинится на roblox.com, и сессия подхватывается здесь.
        Возвращает .ROBLOSECURITY после успеха. Бросает TimeoutError за 5 мин.
        """
        self._refresh_csrf()
        device_id = secrets.token_hex(16)
        r = self._req(CREATE_URL, json.dumps({
            "deviceType": "AdditionalDeviceLogin",
            "identification": True,
        }).encode())
        body = json.loads(r.read())
        deep_link = body.get("deepLink") or body.get("redirectUrl")
        if not deep_link:
            raise RuntimeError("Roblox не вернул ссылку входа")
        on_url(deep_link)
        subprocess.Popen([browser_cmd, deep_link]) if browser_cmd else None

        poll = self._req(POLL_URL, json.dumps({"deviceToken": body["deviceToken"]}).encode())
        deadline = time.time() + 300
        while time.time() < deadline:
            resp = json.loads(poll.read())
            st = resp.get("status")
            on_status(f"статус входа: {st}")
            if st == "Completed":
                token = resp["userTicket"]
                self.store_cookie(token)
                return token
            if st in ("Denied", "Expired", "NotFound"):
                raise RuntimeError(f"вход отклонён ({st})")
            time.sleep(2)
        raise TimeoutError("превышено время ожидания входа (5 мин)")

    # ---------- проверка сессии ----------
    def whoami(self) -> dict:
        token = self._token or self.saved_cookie()
        if not token:
            return {}
        req = urllib.request.Request("https://users.roblox.com/v1/users/authenticated",
                                     headers={"Cookie": f".ROBLOSECURITY={token}"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=15).read())
        except Exception:
            return {}
