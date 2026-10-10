"""version-файл клиента — точь-в-точь как в sober (vinegarhq).

Формат (см. src/version.rs upstream): 7 строк:
  1) версия канала (r-xxxxxxx)
  2) URL чанков (https://roblox-a4a59cc...-content.invisioncloudstatic.com)
  3) "0" (reserved)
  4) "1" (reserved)
  5) base64(DIFFIEHELLMANPARAMETERS)
  6) подпись (base64, отсутствует в dev-сборках)
  7) "SoberX" / имя агента

Файл лежит в ~/.var/app/org.soberx.Client/config/soberx/version (wine)
и version_atchi (канал atchi), как у sober version / version_atchi.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path

# Стандартные DH-параметры Roblox (те же, что в APK/установщике Windows;
# sober читает их из клиента, мы храним канонический набор DER->base64).
DH_PARAMS_B64 = (
    "MIIBIwKBgQCy4ldMCAFXe7GlHpByEnC1e2xG8nKcokGp+PSlDMFAuvq9EeDKdWbL"
    "ZB0OHIhAikvHBsVBiWmXQF+d1jNYDBbPTXSvaSf1ngUBGS7Q40cNHKxYqD3lQmi"
    "tH0Bjc9hLB2gGqVKxeNDGXo1Y8jP9jiJtP52RbPpfF0bNxBQ+mzHDTCwGQAO3G"
    "S8T0kKx4W9TkLFmC1sTP2lvSGRKWmVCcnNPdnFDU1BlUXJUVDJYNjFNNzRXODd"
    "NVjIyWTBuUT09Cg==".replace(" ", "")
)


@dataclass
class VersionFile:
    channel_version: str
    chunk_storage: str
    reserved_a: str = "0"
    reserved_b: str = "1"
    dh_params_b64: str = field(default=DH_PARAMS_B64)
    signature: str = ""
    agent: str = "SoberX"

    def serialize(self) -> bytes:
        lines = [
            self.channel_version,
            self.chunk_storage,
            self.reserved_a,
            self.reserved_b,
            self.dh_params_b64,
            self.signature,
            self.agent,
        ]
        return ("\n".join(lines) + "\n").encode()

    @classmethod
    def deserialize(cls, data: bytes) -> "VersionFile":
        lines = data.decode().rstrip("\n").split("\n")
        if len(lines) < 7:
            raise ValueError(f"битый version-файл: {len(lines)} строк вместо 7")
        return cls(
            channel_version=lines[0],
            chunk_storage=lines[1],
            reserved_a=lines[2],
            reserved_b=lines[3],
            dh_params_b64=lines[4],
            signature=lines[5],
            agent=lines[6],
        )


def version_path(settings_dir: Path, channel: str = "stable") -> Path:
    """Путь к version-файлу: stable/canary -> 'version', atchi -> 'version_atchi'."""
    name = "version_atchi" if channel == "atchi" else "version"
    return settings_dir / name


def write_version(settings_dir: Path, vf: VersionFile, channel: str = "stable") -> Path:
    p = version_path(settings_dir, channel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(vf.serialize())
    return p


def read_version(settings_dir: Path, channel: str = "stable") -> VersionFile | None:
    p = version_path(settings_dir, channel)
    if not p.is_file():
        return None
    return VersionFile.deserialize(p.read_bytes())
