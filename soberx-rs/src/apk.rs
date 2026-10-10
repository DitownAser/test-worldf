//! Работа с кастомными APK Roblox: парсинг AXML-манифеста, валидация,
//! установка в хранилище, извлечение нативных библиотек (порт apk.py).

use anyhow::{anyhow, Result};
use std::fs;
use std::io::{Cursor, Read, Write};
use std::path::{Path, PathBuf};

pub const PUBNUB_CHANNEL: &str = "https://pubnub.robxn.com/android";

#[derive(Debug, Clone)]
pub struct ApkInfo {
    pub path: PathBuf,
    pub package: String,
    pub version_name: String,
    pub version_code: u64,
    pub abi: Vec<String>,
    pub size: u64,
    pub valid: bool,
    pub error: String,
}

/// Извлекает строки из бинарного AndroidManifest.xml (AXML):
/// UTF-16LE последовательности + ASCII-токены.
fn strings_from_axml(raw: &[u8]) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    // UTF-16LE runs >= 2 printable chars
    let mut i = 0;
    while i + 1 < raw.len() {
        if raw[i].is_ascii_graphic() && raw[i + 1] == 0 {
            let start = i;
            let mut s = String::new();
            while i + 1 < raw.len() && raw[i].is_ascii_graphic() && raw[i + 1] == 0 {
                s.push(raw[i] as char);
                i += 2;
            }
            if s.chars().count() >= 2 {
                out.push(s);
            } else {
                i = start + 2;
            }
        } else {
            i += 1;
        }
    }
    // ASCII tokens len>=3
    let mut cur = String::new();
    for &b in raw {
        if b.is_ascii_graphic() || b == b' ' {
            cur.push(b as char);
        } else {
            if cur.len() >= 3 {
                out.push(cur.clone());
            }
            cur.clear();
        }
    }
    if cur.len() >= 3 {
        out.push(cur);
    }
    out.sort();
    out.dedup();
    out
}

fn is_dotted_token(s: &str) -> Option<&str> {
    // com.roblox.client и т.п.: сегенты из [\w.-], >=2 точек, ascii
    let bytes = s.as_bytes();
    let ok = bytes.iter().all(|c| c.is_ascii_alphanumeric() || *c == b'.' || *c == b'_' || *c == b'-');
    if !ok || s.matches('.').count() < 2 || s.len() < 6 {
        return None;
    }
    Some(s)
}

fn looks_like_version(s: &str) -> Option<(String, u64)> {
    // формат 1.6.9999999.1934 — четыре числа, третье 7-9 знаков
    let parts: Vec<&str> = s.split('.').collect();
    if parts.len() != 4 {
        return None;
    }
    for p in &parts[..2] {
        if p.is_empty() || p.len() > 4 || !p.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
    }
    if !(7..=9).contains(&parts[2].len()) || !parts[2].bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if parts[3].is_empty() || parts[3].len() > 4 || !parts[3].bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    Some((s.to_string(), parts[2].parse().unwrap()))
}

fn read_android_manifest(zf: &mut zip::ZipArchive<Cursor<Vec<u8>>>) -> (String, String, u64) {
    let raw = match zf.by_name("AndroidManifest.xml") {
        Ok(mut f) => {
            let mut buf = Vec::new();
            f.read_to_end(&mut buf).unwrap_or(0);
            buf
        }
        Err(_) => return (String::new(), String::new(), 0),
    };
    let strings = strings_from_axml(&raw);
    let text = strings.join("\n");
    let pkg = is_dotted_token(
        text
            .lines()
            .find(|l| l.contains("roblox") && is_dotted_token(l).is_some())
            .or_else(|| text.lines().find(|l| is_dotted_token(l).is_some()))
            .unwrap_or(""),
    )
    .unwrap_or("")
    .to_string();
    let (ver, code) = text
        .lines()
        .filter_map(|l| l.split_whitespace().next())
        .find_map(|tok| looks_like_version(tok))
        .unwrap_or_default();
    (pkg, ver, code)
}

/// Полная инспекция APK без внешних инструментов.
pub fn inspect_apk(path: &Path) -> ApkInfo {
    let bad = |err: &str| ApkInfo {
        path: path.to_path_buf(),
        package: String::new(),
        version_name: String::new(),
        version_code: 0,
        abi: Vec::new(),
        size: fs::metadata(path).map(|m| m.len()).unwrap_or(0),
        valid: false,
        error: err.to_string(),
    };
    if !path.is_file() {
        return bad("файл не найден");
    }
    let data = match fs::read(path) {
        Ok(d) => d,
        Err(_) => return bad("не читается"),
    };
    let size = data.len() as u64;
    let mut zf = match zip::ZipArchive::new(Cursor::new(data)) {
        Ok(z) => z,
        Err(_) => {
            return ApkInfo {
                path: path.to_path_buf(),
                package: String::new(),
                version_name: String::new(),
                version_code: 0,
                abi: Vec::new(),
                size,
                valid: false,
                error: "не является zip/APK".into(),
            }
        }
    };

    let names: Vec<String> = zf.file_names().map(|s| s.to_string()).collect();
    let mut abis: Vec<String> = names
        .iter()
        .filter_map(|n| n.strip_prefix("lib/")?.split('/').next().map(|a| a.to_string()))
        .collect();
    abis.sort();
    abis.dedup();

    let has_client = names.iter().any(|n| {
        n.starts_with("assets/ClientContent.xml")
            || n == "assets/ClientVersion.xml"
            || (n.starts_with("lib/") && (n.ends_with("/libroblox.so") || n.ends_with("/librogbox.so")))
            || (n.starts_with("assets/") && n.ends_with(".bundle"))
    });
    let (pkg, ver, code) = read_android_manifest(&mut zf);

    let is_roblox = pkg.to_lowercase().contains("roblox") || has_client;
    ApkInfo {
        path: path.to_path_buf(),
        package: pkg,
        version_name: ver,
        version_code: code,
        abi: abis,
        size,
        valid: is_roblox,
        error: if is_roblox {
            String::new()
        } else {
            "похоже, это не Roblox APK (нет пакетов/ассетов Roblox)".into()
        },
    }
}

/// Скачать официальный Android-APK с канала релизов.
pub fn download_official(dest_dir: &Path) -> Result<PathBuf> {
    fs::create_dir_all(dest_dir)?;
    let body = crate::download::get_bytes(PUBNUB_CHANNEL)?;
    let j: serde_json::Value = serde_json::from_slice(&body)?;
    let url = if let Some(o) = j.get("url").and_then(|v| v.as_str()) {
        o.to_string()
    } else if let Some(arr) = j.as_array().and_then(|a| a.first()).and_then(|v| v.get("url")).and_then(|v| v.as_str()) {
        arr.to_string()
    } else {
        return Err(anyhow!("канал не вернул URL"));
    };
    let name = Path::new(&url).file_name().unwrap_or_default().to_string_lossy().to_string();
    let out = dest_dir.join(format!("official-{name}"));
    crate::download::download(&url, &out, None, None)
}

/// Валидирует и кладёт APK в хранилище SoberX (копия с именем версии).
pub fn install_apk(apk: &Path, store_dir: &Path) -> Result<PathBuf> {
    let info = inspect_apk(apk);
    if !info.valid {
        let msg = if info.error.is_empty() { "APK не прошёл проверку".to_string() } else { info.error.clone() };
        return Err(anyhow!(msg));
    }
    fs::create_dir_all(store_dir)?;
    let name = format!(
        "{}_{}.apk",
        if info.package.is_empty() { "custom" } else { &info.package },
        if info.version_name.is_empty() { "v0" } else { &info.version_name }
    );
    let dst = store_dir.join(name);
    fs::copy(apk, &dst)?;
    Ok(dst)
}

/// Извлекает нативные библиотеки (.so) нужной ABI из APK.
pub fn extract_native_libs(apk: &Path, dest: &Path, abi: Option<&str>) -> Result<Vec<PathBuf>> {
    fs::create_dir_all(dest)?;
    let data = fs::read(apk)?;
    let mut zf = zip::ZipArchive::new(Cursor::new(data))?;
    let names: Vec<String> = zf.file_names().map(|s| s.to_string()).collect();
    let abis: Vec<String> = match abi {
        Some(a) => vec![a.to_string()],
        None => {
            let mut v: Vec<String> = names
                .iter()
                .filter_map(|n| n.strip_prefix("lib/")?.split('/').next().map(|a| a.to_string()))
                .collect();
            v.sort();
            v.dedup();
            v
        }
    };
    let mut out = Vec::new();
    for a in &abis {
        for n in &names {
            if let Some(rest) = n.strip_prefix(&format!("lib/{a}/")) {
                if !rest.ends_with(".so") || rest.contains('/') {
                    continue;
                }
                let tgt = dest.join(a).join(rest);
                fs::create_dir_all(tgt.parent().unwrap())?;
                let mut f = zf.by_name(n)?;
                let mut buf = Vec::new();
                f.read_to_end(&mut buf)?;
                fs::File::create(&tgt)?.write_all(&buf)?;
                out.push(tgt);
            }
        }
    }
    Ok(out)
}

/// Список установленных APK в хранилище.
pub fn installed_list(store_dir: &Path) -> Vec<ApkInfo> {
    let mut res = Vec::new();
    if let Ok(rd) = fs::read_dir(store_dir) {
        let mut files: Vec<_> = rd
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| p.extension().map(|x| x == "apk").unwrap_or(false))
            .collect();
        files.sort();
        for p in files {
            res.push(inspect_apk(&p));
        }
    }
    res
}

/// Установить APK на запущенный Android-эмулятор через adb (если доступен).
pub fn run_on_emulator(apk: &Path, serial: Option<&str>) -> Result<std::process::Output> {
    let mut cmd = std::process::Command::new("adb");
    if let Some(s) = serial {
        cmd.args(["-s", s]);
    }
    cmd.args(["install", "-r"]).arg(apk);
    cmd.output().map_err(|e| anyhow!("adb: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_apk(dir: &Path, pkg: &str, version: &str, roblox: bool) -> PathBuf {
        let p = dir.join(if roblox { "rbx.apk" } else { "other.apk" });
        let file = fs::File::create(&p).unwrap();
        let mut w = zip::ZipWriter::new(file);
        let opts = zip::write::SimpleFileOptions::default();
        // манифест: UTF-16LE строки как в AXML
        let mut manifest = Vec::new();
        for s in [pkg, version, "com.example.other"] {
            for u in s.encode_utf16() {
                manifest.extend_from_slice(&u.to_le_bytes());
            }
            manifest.push(0);
            manifest.push(0);
        }
        w.start_file("AndroidManifest.xml", opts).unwrap();
        w.write_all(&manifest).unwrap();
        if roblox {
            w.start_file("lib/arm64-v8a/libroblox.so", opts).unwrap();
            w.write_all(b"\x7fELFfake").unwrap();
            w.start_file("assets/ClientVersion.xml", opts).unwrap();
            w.write_all(b"<xml/>").unwrap();
        }
        w.finish().unwrap();
        p
    }

    #[test]
    fn valid_roblox_apk() {
        let dir = std::env::temp_dir().join(format!("soberx-apk-test-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let apk = make_apk(&dir, "com.roblox.client", "1.6.9999999.1934", true);
        let info = inspect_apk(&apk);
        assert!(info.valid, "ошибка: {}", info.error);
        assert_eq!(info.package, "com.roblox.client");
        assert_eq!(info.version_name, "1.6.9999999.1934");
        assert_eq!(info.version_code, 9999999);
        assert_eq!(info.abi, vec!["arm64-v8a".to_string()]);

        let libs = extract_native_libs(&apk, &dir.join("libs"), Some("arm64-v8a")).unwrap();
        assert_eq!(libs.len(), 1);
        assert!(libs[0].ends_with("libroblox.so"));

        let stored = install_apk(&apk, &dir.join("store")).unwrap();
        assert!(stored.is_file());
        assert_eq!(installed_list(&dir.join("store")).len(), 1);
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn rejects_non_roblox() {
        let dir = std::env::temp_dir().join(format!("soberx-apk-neg-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let apk = make_apk(&dir, "org.fdroid.repo", "1.0.1234567.1", false);
        let info = inspect_apk(&apk);
        assert!(!info.valid);
        assert!(install_apk(&apk, &dir.join("store")).is_err());
        fs::remove_dir_all(&dir).ok();
    }
}
