//! Авторизация Roblox: web-вход через redirect на localhost:59251 (flow как у sober)
//! + хранение .ROBLOSECURITY в libsecret (secret-tool) или файле 0600.

use anyhow::{anyhow, Context, Result};
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::Command;
use std::sync::{Arc, Mutex};

pub const AUTH_PORT: u16 = 59251; // тот же порт обратного вызова, что у официального клиента

fn cookie_file(settings_dir: &PathBuf) -> PathBuf {
    settings_dir.join("authinfo.json")
}

/// Читаем сохранённый токен: сначала libsecret, затем файл.
pub fn saved_cookie(settings_dir: &PathBuf) -> Option<String> {
    if let Ok(out) = Command::new("secret-tool")
        .args(["lookup", "service", "soberx", "account", "roblox"])
        .output()
    {
        if out.status.success() {
            let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if !s.is_empty() {
                return Some(s);
            }
        }
    }
    let data = std::fs::read_to_string(cookie_file(settings_dir)).ok()?;
    let j: serde_json::Value = serde_json::from_str(&data).ok()?;
    j["token"].as_str().map(|s| s.to_string())
}

pub fn store_cookie(settings_dir: &PathBuf, token: &str) -> Result<()> {
    let secret_ok = (|| -> Result<bool> {
        let mut child = Command::new("secret-tool")
            .arg("store")
            .arg("--label=SoberX Roblox")
            .args(["service", "soberx", "account", "roblox"])
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::null())
            .spawn()?;
        child.stdin.take().unwrap().write_all(token.as_bytes())?;
        Ok(child.wait()?.success())
    })()
    .unwrap_or(false);

    if secret_ok {
        let _ = std::fs::remove_file(cookie_file(settings_dir));
        return Ok(());
    }
    std::fs::create_dir_all(settings_dir)?;
    std::fs::write(
        cookie_file(settings_dir),
        serde_json::json!({ "token": token }).to_string(),
    )?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(cookie_file(settings_dir), std::fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

pub fn logout(settings_dir: &PathBuf) {
    let _ = std::fs::remove_file(cookie_file(settings_dir));
    let _ = Command::new("secret-tool")
        .args(["clear", "service", "soberx"])
        .output();
}

/// Поднять localhost:59251 и дождаться ROBLOSECURITY из редиректа браузера.
pub fn wait_for_token(timeout_secs: u64) -> Option<String> {
    let listener = TcpListener::bind(("127.0.0.1", AUTH_PORT)).ok()?;
    let token = Arc::new(Mutex::new(None::<String>));
    let tx = token.clone();

    let handle = std::thread::spawn(move || {
        for stream in listener.incoming() {
            if tx.lock().unwrap().is_some() {
                break;
            }
            let Ok(mut stream) = stream else { continue };
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut line = String::new();
            if reader.read_line(&mut line).is_err() {
                continue;
            }
            // "GET /auth?ROBLOSECURITY=... HTTP/1.1" — дочитываем заголовки
            loop {
                let mut hdr = String::new();
                match reader.read_line(&mut hdr) {
                    Ok(0) => break,
                    Ok(_) => {
                        if hdr.trim().is_empty() {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
            let path = line
                .split_whitespace()
                .nth(1)
                .unwrap_or("/")
                .to_string();
            let query = path.split_once('?').map(|(_, q)| q).unwrap_or("");
            let tok = query
                .split('&')
                .find_map(|kv| kv.strip_prefix("ROBLOSECURITY="))
                .map(percent_decode);
            let resp = if path.starts_with("/auth") && tok.is_some() {
                let t = tok.clone().unwrap();
                *tx.lock().unwrap() = Some(t);
                "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n<h2>SoberX: вход выполнен, можно закрыть окно.</h2>"
            } else {
                "HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"
            };
            let _ = stream.write_all(resp.as_bytes());
            let _ = stream.flush();
            if tx.lock().unwrap().is_some() {
                break;
            }
        }
    });

    let end = std::time::Instant::now() + std::time::Duration::from_secs(timeout_secs);
    let result = loop {
        if let Some(t) = token.lock().unwrap().clone() {
            break Some(t);
        }
        if std::time::Instant::now() >= end {
            break None;
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    };
    let _ = handle;
    result
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'%' if i + 2 < bytes.len() => {
                if let Ok(b) = u8::from_str_radix(&s[i + 1..i + 3], 16) {
                    out.push(b);
                    i += 3;
                    continue;
                }
                out.push(bytes[i]);
                i += 1;
            }
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            c => {
                out.push(c);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).to_string()
}

/// Полная авторизация: открыть браузер с ссылкой входа и дождаться токена.
pub fn login_interactive(browser_cmd: &str, on_status: &dyn Fn(&str)) -> Result<String> {
    let url = format!(
        "https://www.roblox.com/login?mode=redirect&signIn=true&source=Desktop&redirect_uri=http://localhost:{AUTH_PORT}/auth"
    );
    on_status(&format!("открой в браузере: {url}"));
    let _ = Command::new(browser_cmd).arg(&url).spawn();
    let tok = wait_for_token(300).ok_or_else(|| anyhow!("не получили токен за 5 минут"))?;
    on_status("вход выполнен");
    Ok(tok)
}

/// best-effort: имя пользователя по .ROBLOSECURITY через auth sync endpoint
pub fn username_from_token(token: &str) -> Option<String> {
    let j: serde_json::Value = ureq::get("https://apis.roproxy.com/auth/v2/usernamesync")
        .set("Cookie", &format!(".ROBLOSECURITY={token}"))
        .set("User-Agent", "SoberX/1.0")
        .timeout(std::time::Duration::from_secs(15))
        .call()
        .ok()
        .and_then(|r| r.into_json().ok())
        .context("usernamesync")
        .ok()?;
    j["userName"]
        .as_str()
        .or_else(|| j["username"].as_str())
        .map(|s| s.to_string())
}

/// whoami через users.roblox.com
pub fn whoami(token: &str) -> Option<serde_json::Value> {
    ureq::get("https://users.roblox.com/v1/users/authenticated")
        .set("Cookie", &format!(".ROBLOSECURITY={token}"))
        .set("User-Agent", "SoberX/1.0")
        .timeout(std::time::Duration::from_secs(15))
        .call()
        .ok()
        .and_then(|r| r.into_json().ok())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn percent_decodes() {
        assert_eq!(percent_decode("a%2Fb+c"), "a/b c");
    }

    #[test]
    fn catches_redirect_token() {
        // стучимся руками на localhost:59251 как браузер после логина
        let t = std::thread::spawn(|| wait_for_token(10));
        std::thread::sleep(std::time::Duration::from_millis(300));
        let mut stream = std::net::TcpStream::connect("127.0.0.1:59251").unwrap();
        use std::io::Write;
        stream
            .write_all(b"GET /auth?ROBLOSECURITY=%7Btok%7D HTTP/1.1\r\nHost: localhost\r\n\r\n")
            .unwrap();
        let tok = t.join().unwrap();
        assert_eq!(tok.as_deref(), Some("{tok}"));
    }
}
