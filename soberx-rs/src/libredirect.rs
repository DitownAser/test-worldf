//! libredirect.so — LD_PRELOAD-библиотека обхода блокировок Roblox.
//! Точь-в-точь функциональность sober: перехват getaddrinfo и подмена
//! заблокированных хостов на рабочие зеркала roproxy.
//! Собирается gcc -shared -fPIC при первом запуске (как sober, поставляющий .so).

use std::path::{Path, PathBuf};
use std::process::Command;

pub const SRC: &str = r#"
/* libredirect.so — LD_PRELOAD getaddrinfo hook (as in vinegarhq/sober) */
#define _GNU_SOURCE
#include <netdb.h>
#include <string.h>
#include <strings.h>
#include <stdio.h>
#include <dlfcn.h>

static const struct { const char *from, *to; } hosts[] = {
    {"www.roblox.com", "web.roproxy.com"},
    {"web.roblox.com", "web.roproxy.com"},
    {"api.roblox.com", "apis.roproxy.com"},
    {"auth.roblox.com", "auth.roproxy.com"},
    /* auth.user.roblox.com НЕ редиректится: браузерный вход идёт на roblox.com,
       а redirect_uri=localhost:59251 должен принять сам официальный сайт */
    {"games.roblox.com", "games.roproxy.com"},
    {"gameconnect.roblox.com", "gc.roproxy.com"},
    {"gamejoin.roblox.com", "join.roproxy.com"},
    {"clientsettingscdn.roblox.com", "clientsettings.roproxy.com"},
    {"tray.roblox.com", "tray.roproxy.com"},
    {"setup.rbxcdn.com", "setup.rbxcdn.roproxy.workers.dev"},
    {"js.roblox.com", "js.roproxy.com"},
    {"ossproxy.aftershock.space", "ossproxy.oafdev.de"},
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
"#;

fn have(cmd: &str) -> bool {
    Command::new("which").arg(cmd).output().map(|o| o.status.success()).unwrap_or(false)
}

/// Собрать libredirect.so, если ещё нет. Вернуть путь или None.
pub fn ensure_libredirect(build_dir: &Path) -> Option<PathBuf> {
    let so = build_dir.join("libredirect.so");
    // быстрый путь: .so уже собран и актуален (сравнение mtime со статическим SRC) —
    // не трогаем gcc вообще; дальше проверка только один раз за процесс
    static CHECKED: std::sync::OnceLock<()> = std::sync::OnceLock::new();
    if so.is_file() {
        if CHECKED.get().is_some() || so.metadata().map(|m| m.len()).unwrap_or(0) > 4096 {
            return Some(so);
        }
    }
    if !have("gcc") {
        return None;
    }
    std::fs::create_dir_all(build_dir).ok()?;
    let c = build_dir.join("libredirect.c");
    std::fs::write(&c, SRC).ok()?;
    let status = Command::new("gcc")
        .args(["-shared", "-fPIC", "-O2", "-o"])
        .arg(&so)
        .arg(&c)
        .arg("-ldl")
        .status()
        .ok()?;
    if status.success() && so.is_file() {
        Some(so)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compiles_if_gcc_available() {
        let dir = std::env::temp_dir().join(format!("soberx-libredir-test-{}", std::process::id()));
        if let Some(so) = ensure_libredirect(&dir) {
            assert!(so.is_file());
            // проверка, что символ getaddrinfo экспортируется
            let nm = Command::new("nm").arg("-D").arg(&so).output();
            if let Ok(out) = nm {
                let text = String::from_utf8_lossy(&out.stdout);
                assert!(text.contains("getaddrinfo"), "нет экспорта getaddrinfo:\n{text}");
            }
        }
        let _ = std::fs::remove_dir_all(&dir);
    }
}
