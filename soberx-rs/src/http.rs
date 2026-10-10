//! Единая HTTP-фасад SoberX (аналог soberx/http.py в Python-пакете).
//!
//! Раньше транспорт был размазан по трём местам: `fasthttp::get_bytes`
//! (keep-alive пул + ureq-агент), `download::get_bytes` (свой ureq-запрос) и
//! сырые `ureq::get(...)` внутри `auth`. Этот модуль собирает всё в одну
//! точку: общий User-Agent и таймауты.
//!
//! - `get_bytes` — тело ответа в память (быстрый путь fasthttp для http://,
//!   shared-агент для https://);
//! - `get_json` — то же плюс разбор JSON;
//! - `get_json_with_cookie` — GET с cookie авторизации (best-effort вызовы).

use anyhow::{anyhow, Context, Result};
use std::time::Duration;

pub const USER_AGENT: &str = "SoberX/1.0";
/// Короткий таймаут для интерактивных auth-запросов (whoami и т.п.).
pub const AUTH_TIMEOUT: Duration = Duration::from_secs(15);

/// GET тела ответа в байты. Делегирует `fasthttp` (пул keep-alive + общий агент).
#[inline]
pub fn get_bytes(url: &str) -> Result<Vec<u8>> {
    crate::fasthttp::get_bytes(url)
}

/// GET с произвольными заголовками и заданным таймаутом.
fn get_with_headers(url: &str, headers: &[(&str, String)], timeout: Duration) -> Result<String> {
    let mut req = ureq::AgentBuilder::new()
        .user_agent(USER_AGENT)
        .timeout_connect(crate::fasthttp::CONNECT_TIMEOUT)
        .timeout(timeout)
        .build()
        .get(url);
    for (k, v) in headers {
        req = req.set(k, v);
    }
    let resp = req.call().with_context(|| format!("GET {url}"))?;
    if resp.status() != 200 {
        return Err(anyhow!("HTTP {} для {url}", resp.status()));
    }
    let mut buf = String::new();
    use std::io::Read;
    resp.into_reader().read_to_string(&mut buf)?;
    Ok(buf)
}

/// Разобрать JSON из ответа GET (через быстрый путь fasthttp).
pub fn get_json(url: &str) -> Result<serde_json::Value> {
    let data = get_bytes(url)?;
    serde_json::from_slice(&data).with_context(|| format!("битый JSON из {url}"))
}

/// GET JSON с Cookie: .ROBLOSECURITY=<token> (best-effort вызовы авторизации).
pub fn get_json_with_cookie(url: &str, token: &str) -> Option<serde_json::Value> {
    get_with_headers(url, &[("Cookie", format!(".ROBLOSECURITY={token}"))], AUTH_TIMEOUT)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
}
