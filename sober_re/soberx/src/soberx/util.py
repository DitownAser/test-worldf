"""Мелкие утилиты, общие для CLI/GUI/инсталлятора."""
from __future__ import annotations

import shutil


def have(cmdname: str) -> bool:
    """Есть ли исполняемая программа в PATH."""
    return shutil.which(cmdname) is not None
