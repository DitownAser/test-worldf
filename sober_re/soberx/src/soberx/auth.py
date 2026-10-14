"""Авторизация Roblox через веб-вход (flow как у sober: WebView/browser + cookie).

Результат — .ROBLOSECURITY cookie, сохраняемая в libsecret (если доступен)
или в файл с правами 0600.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Callable

from .http import http_post_json, open_url

AUTH_BASE = "https://auth.roblox.com"
CSRF_URL = f"{AUTH_BASE}/v2/logout"
POLL_URL = f"{AUTH_BASE}/v2/authentication/login/check"
CREATE_URL = f"{AUTH_BASE}/v2/authentication/login/create"
USERS_AUTHENTICATED_URL = "https://users.roblox.com/v1/users/authenticated"

OnStatus = Callable[[str], None]       # текстовый статус
OnUrl = Callable[[str], None]          # ссылка для открытия в браузере

_SECRET_ATTRS = ("service", "soberx", "account", "roblox")


class AuthManager:
    def __init__(self, settings_path: Path):
        self._cookie_file = settings_path / "authinfo.json"
        self._token: str | None = None
        self._csrf: str | None = None

    # ---------- хранение ----------
    def _secret_tool(self, *args: str, stdin: bytes | None = None,
                     timeout: int = 5) -> subprocess.CompletedProcess | None:
        """Запуск secret-tool; None, если libsecret недоступна."""
        try:
            return subprocess.run(["secret-tool", *args], input=stdin,
                                  capture_output=True, text=stdin is not None,
                                  timeout=timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def saved_cookie(self) -> str | None:
        """Читаем сохранённый токен: сначала libsecret, затем файл."""
        out = self._secret_tool("lookup", *_SECRET_ATTRS)
        if out is not None and out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
        try:
            return json.loads(self._cookie_file.read_text())["token"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            return None

    def store_cookie(self, token: str) -> None:
        p = self._secret_tool("store", "--label=SoberX Roblox", *_SECRET_ATTRS,
                              stdin=token.encode(), timeout=10)
        if p is not None and p.returncode == 0:
            self._cookie_file.unlink(missing_ok=True)
        else:
            self._cookie_file.parent.mkdir(parents=True, exist_ok=True)
            self._cookie_file.write_text(json.dumps({"token": token}))
            self._cookie_file.chmod(0o600)
        self._token = token

    def logout(self) -> None:
        self._token = None
        self._cookie_file.unlink(missing_ok=True)
        self._secret_tool("clear", "service", "soberx")

    # ---------- web flow ----------
    def _refresh_csrf(self) -> None:
        try:
            with http_post_json(CSRF_URL, {}) as r:
                self._csrf = r.headers.get("x-csrf-token")
        except Exception:
            self._csrf = None

    def _post(self, url: str, payload: dict):
        headers = {"x-csrf-token": self._csrf} if self._csrf else None
        return http_post_json(url, payload, extra_headers=headers)

    def login_interactive(self, browser_cmd: str, on_status: OnStatus,
                          on_url: OnUrl) -> str:
        """Веб-вход без пароля в UI: создаём deep-link и ждём подтверждения.

        Аналогично sober: пользователь открывает ссылку в браузере,
        логинится на roblox.com, и сессия подхватывается здесь.
        Возвращает .ROBLOSECURITY после успеха. Бросает TimeoutError за 5 мин.
        """
        self._refresh_csrf()
        body = json.loads(self._post(CREATE_URL, {
            "deviceType": "AdditionalDeviceLogin",
            "identification": True,
        }).read())
        deep_link = body.get("deepLink") or body.get("redirectUrl")
        if not deep_link:
            raise RuntimeError("Roblox не вернул ссылку входа")
        on_url(deep_link)
        if browser_cmd:
            subprocess.Popen([browser_cmd, deep_link])

        poll = self._post(POLL_URL, {"deviceToken": body["deviceToken"]})
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
        """Информация о текущем аккаунте ({} если не авторизован/нет сети)."""
        token = self._token or self.saved_cookie()
        if not token:
            return {}
        try:
            with open_url(USERS_AUTHENTICATED_URL, method="GET", timeout=15,
                          headers={"Cookie": f".ROBLOSECURITY={token}"}) as r:
                return json.loads(r.read())
        except Exception:
            return {}
