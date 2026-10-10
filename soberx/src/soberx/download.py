"""Загрузка файлов с прогрессом и SHA-256 проверкой."""
from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path
from typing import Callable

ProgressCb = Callable[[int, int], None]  # (получено, всего)


def download(url: str, dest: Path, progress: ProgressCb | None = None,
             sha256: str | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "SoberX/1.0"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length", "0"))
        done = 0
        with open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if sha256 and h.hexdigest() != sha256.lower():
        tmp.unlink(missing_ok=True)
        raise ValueError(f"SHA-256 не совпал для {url}")
    shutil.move(tmp, dest)
    return dest
