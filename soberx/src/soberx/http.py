"""Единая HTTP-прослойка SoberX: User-Agent, GET/POST с JSON и скачивание файлов.

Ранее каждый модуль (version, download, auth, apk, wineclient) сам строил
``urllib.request.Request`` со своим заголовком User-Agent — здесь этот код
сведён в одно место.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

USER_AGENT = "SoberX/1.0"

ProgressCb = Callable[[int, int], None]  # (получено, всего)


def _request(url: str, data: bytes | None = None, method: str | None = None,
             headers: Mapping[str, str] | None = None) -> urllib.request.Request:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, data=data, method=method, headers=hdrs)


def open_url(url: str, *, data: bytes | None = None, method: str | None = None,
             headers: Mapping[str, str] | None = None, timeout: int = 30):
    """Открыть URL через urllib с единым набором заголовков."""
    return urllib.request.urlopen(_request(url, data, method, headers), timeout=timeout)


def http_get(url: str, timeout: int = 30) -> bytes:
    """Простой GET целиком в память."""
    with open_url(url, method="GET", timeout=timeout) as r:
        return r.read()


def http_get_json(url: str, timeout: int = 30) -> Any:
    """GET + разбор JSON-ответа."""
    return json.loads(http_get(url, timeout).decode())


def http_post_json(url: str, payload: dict, extra_headers: Mapping[str, str] | None = None,
                   timeout: int = 30):
    """POST JSON-тела; возвращает открытый ответ (читайте ``.read()`` сами)."""
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return open_url(url, data=data, method="POST", headers=headers, timeout=timeout)


def download_file(url: str, dest: Path, *, progress: ProgressCb | None = None,
                  sha256: str | None = None, timeout: int = 60,
                  chunk_size: int = 1 << 20) -> Path:
    """Скачать файл в ``dest`` с прогрессом и опциональной проверкой SHA-256.

    Пишется во временный ``*.part``-файл и переносится на место только после
    успешной проверки — обрыв сети не оставляет битой цели.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    done = 0
    try:
        with open_url(url, method="GET", timeout=timeout) as r:
            total = int(r.headers.get("Content-Length", "0"))
            with open(tmp, "wb") as f:
                while chunk := r.read(chunk_size):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if sha256 and h.hexdigest() != sha256.lower():
            raise ValueError(f"SHA-256 не совпал для {url}")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
