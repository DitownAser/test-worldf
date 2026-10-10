//! Версии Roblox и URL чанков — порт src/soberx/version.py (схема vinegarhq/sober).

use anyhow::{anyhow, Context, Result};
use std::path::Path;

pub const VERSION_URL: &str = "https://setup.rbxcdn.com/version";
pub const CLIENT_URL: &str = "https://clientsettingscdn.roblox.com/v2/client-version/WindowsAppLog";

pub const DEFAULT_CHUNK_STORAGE: &str =
    "https://roblox-1eb8602b03ee7600c9b97d8aa07d1095content.content.invisioncloudstatic.com";

/// Файлы клиента, которые sober качает из чанков (wine-дистрибуция).
pub const CLIENT_CHUNKS: &[&str] = &[
    "RobloxPlayerBeta.exe",
    "AppLaunch.dll",
    "Microsoft.WindowsAppRuntime.Bootstrap.dll",
    "c1.dll", "c2.dll", "c3.dll", "c4.dll", "c5.dll",
    "nativehtml_1.dll", "nativehtml_2.dll", "nativehtml_3.dll",
    "VideoDecodingExtensionManifest.xml",
    "rbxcrash-handler.exe",
    "data.prf",
];

fn get(url: &str) -> Result<Vec<u8>> {
    let resp = ureq::get(url)
        .set("User-Agent", "SoberX/1.0")
        .timeout(std::time::Duration::from_secs(60))
        .call()
        .with_context(|| format!("GET {url}"))?;
    let mut buf = Vec::new();
    resp.into_reader().read_to_end(&mut buf)?;
    Ok(buf)
}

/// Актуальная версия клиента (r-xxxxxxx).
pub fn current_version() -> Result<String> {
    if let Ok(data) = get(CLIENT_URL) {
        let j: serde_json::Value = serde_json::from_slice(&data)?;
        if let Some(v) = j["clientVersionUpload"].as_str() {
            return Ok(v.to_string());
        }
    }
    let v = String::from_utf8(get(VERSION_URL)?)?.trim().to_string();
    let ok = v.len() >= 9
        && v.as_bytes()[0].is_ascii_lowercase()
        && v.as_bytes()[1] == b'-'
        && v[2..].bytes().all(|b| b.is_ascii_hexdigit())
        && v[2..].len() == 7;
    if !ok {
        return Err(anyhow!("некорректный ответ version: {v:?}"));
    }
    Ok(v)
}

/// Версия по каналу: stable | canary | atchi | legacy_avi.
pub fn channel_version(channel: &str) -> Result<String> {
    let url = match channel {
        "stable" => CLIENT_URL,
        "canary" => "https://clientsettingscdn.roblox.com/v2/client-version/WindowsCanary",
        "atchi" => "https://clientsettingscdn.roblox.com/v2/client-version/WindowsAtch1",
        "legacy_avi" => "https://clientsettingscdn.roblox.com/v2/client-version/WindowsChannel-AVI",
        _ => return Err(anyhow!("неизвестный канал: {channel}")),
    };
    let data = get(url)?;
    let j: serde_json::Value = serde_json::from_slice(&data)?;
    j["clientVersionUpload"]
        .as_str()
        .map(|s| s.to_string())
        .ok_or_else(|| anyhow!("нет clientVersionUpload в ответе {url}"))
}

/// URL оф. установщика Windows — источник DLL для Wine-префикса.
pub fn bootstrapper_url(version: &str) -> String {
    format!("https://setup.rbxcdn.com/{version}-RobloxInstall.exe")
}

pub fn setup_base_url(version: &str) -> String {
    format!("https://setup.rbxcdn.com/{version}")
}

/// URL чанк-хранилища: читаем из официального Android APK (assets/Roblox/version,
/// строка 2), как делает sober через AndroidChannel; при ошибке — канонический CDN.
pub fn chunk_storage_for(_version: &str, channel: &str) -> String {
    if matches!(channel, "stable" | "canary" | "atchi") {
        if let Ok(storage) = storage_from_apk() {
            return storage;
        }
    }
    DEFAULT_CHUNK_STORAGE.to_string()
}

fn storage_from_apk() -> Result<String> {
    let data = get(
        "https://clientsettingscdn.roblox.com/v2/client-version/AndroidPlatform",
    )?;
    let j: serde_json::Value = serde_json::from_slice(&data)?;
    let u = j["clientVersionUpload"]
        .as_str()
        .ok_or_else(|| anyhow!("нет версии Android"))?
        .to_string();
    let apk = get(&format!("https://setup.rbxcdn.com/{u}-roblox.apk"))?;
    let reader = std::io::Cursor::new(apk);
    let mut zf = zip::ZipArchive::new(reader)?;
    let mut vf = String::new();
    {
        let mut f = zf.by_name("assets/Roblox/version")?;
        f.read_to_string(&mut vf)?;
    }
    vf.lines()
        .nth(1)
        .map(|s| s.trim().to_string())
        .ok_or_else(|| anyhow!("битый version в APK"))
}

/// Базовый URL чанков: <storage>/content/<version>/
pub fn chunks_base(version: &str, storage: &str) -> String {
    format!("{}/content/{}/", storage.trim_end_matches('/'), version)
}

/// Скачать securitychecks.qjs.js (нужен клиенту, как в sober).
pub fn get_qjs(version: &str, storage: &str, dest_dir: &Path) -> Result<std::path::PathBuf> {
    let url = format!("{}securitychecks.qjs.js", chunks_base(version, storage));
    crate::download::download(&url, &dest_dir.join("securitychecks.qjs.js"), None, None)
}

/// Скачать все чанки клиента в versions/<version> (точная логика sober).
/// Возвращает список успешно скачанных файлов.
pub fn download_client_chunks(
    version: &str,
    storage: &str,
    dest_dir: &Path,
) -> Vec<String> {
    let mut got = Vec::new();
    for name in CLIENT_CHUNKS {
        let url = format!("{}{}", chunks_base(version, storage), name);
        match crate::download::download(&url, &dest_dir.join(name), None, None) {
            Ok(_) => got.push((*name).to_string()),
            Err(_) => continue, // часть чанков может отсутствовать на старых версиях
        }
    }
    got
}

use std::io::Read;
