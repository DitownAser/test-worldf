"""libredirect.so — LD_PRELOAD-библиотека обхода блокировок Roblox.

Точь-в-точь функциональность sober: перехват getaddrinfo и подмена
заблокированных хостов на рабочие зеркала:
  www.roblox.com      -> apis.roproxy.com
  clientsettingscdn   -> clientsettings.roproxy.com
  setup.rbxcdn.com    -> setup.rbxcdn.roproxy.workers.dev
  gamejoin          -> join.roproxy.com
Собирается gcc -shared -fPIC -o libredirect.so libredirect.c при первом
запуске (как это делает sober, поставляя готовый .so). Если gcc нет —
используется python-fallback через socket monkeypatch для наших модулей.
"""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

SRC = r"""
/* libredirect.so — LD_PRELOAD getaddrinfo hook (as in vinegarhq/sober) */
#define _GNU_SOURCE
#include <netdb.h>
#include <string.h>
#include <stdio.h>
#include <dlfcn.h>

static const struct { const char *from, *to; } hosts[] = {
    {"www.roblox.com", "apis.roproxy.com"},
    {"web.roblox.com", "web.roproxy.com"},
    {"setup.rbxcdn.com", "setup.rbxcdn.roproxy.workers.dev"},
    {"clientsettingscdn.roblox.com", "clientsettings.roproxy.com"},
    {"gamejoin.roblox.com", "join.roproxy.com"},
    {"api.roblox.com", "api.roproxy.com"},
    {"auth.roblox.com", "auth.roproxy.com"},
    {NULL, NULL}
};

int getaddrinfo(const char *node, const char *service,
                const struct addrinfo *hints, struct addrinfo **res) {
    int (*real)(const char*, const char*, const struct addrinfo*, struct addrinfo**);
    real = dlsym(RTLD_NEXT, "getaddrinfo");
    const char *mapped = node;
    if (node) {
        for (int i = 0; hosts[i].from; i++)
            if (!strcasecmp(node, hosts[i].from)) { mapped = hosts[i].to; break; }
    }
    return real(mapped, service, hints, res);
}
"""


def ensure_libredirect(build_dir: Path) -> Path | None:
    """Собрать libredirect.so, если ещё нет. Вернуть путь или None."""
    so = build_dir / "libredirect.so"
    if so.is_file():
        return so
    if not shutil.which("gcc"):
        return None
    build_dir.mkdir(parents=True, exist_ok=True)
    c = build_dir / "libredirect.c"
    c.write_text(SRC)
    try:
        subprocess.run(
            ["gcc", "-shared", "-fPIC", "-O2", "-o", str(so), str(c), "-ldl"],
            check=True, timeout=120, capture_output=True,
        )
        return so if so.is_file() else None
    except Exception:
        return None
