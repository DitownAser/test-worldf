"""Загрузка файлов с прогрессом и SHA-256 проверкой.

Реализация вынесена в ``soberx.http.download_file``; модуль сохранён как
публичный API пакета (``from .download import download``).
"""
from __future__ import annotations

from pathlib import Path

from .http import ProgressCb, download_file


def download(url: str, dest: Path, progress: ProgressCb | None = None,
             sha256: str | None = None) -> Path:
    """Скачать ``url`` в ``dest`` с необязательным прогрессом и проверкой SHA-256."""
    return download_file(url, dest, progress=progress, checksum=sha256,
                         checksum_algo="sha256")
