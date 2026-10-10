//! Загрузка файлов с прогрессом и проверкой SHA-256 (порт download.py).

use anyhow::{anyhow, Context, Result};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

pub fn download(
    url: &str,
    dest: &Path,
    mut progress: Option<&mut dyn FnMut(u64, u64)>,
    sha256: Option<&str>,
) -> Result<PathBuf> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = dest.with_extension(format!(
        "{}.part",
        dest.extension().and_then(|e| e.to_str()).unwrap_or("tmp")
    ));

    let resp = ureq::get(url)
        .set("User-Agent", "SoberX/1.0")
        .timeout(std::time::Duration::from_secs(120))
        .call()
        .with_context(|| format!("GET {url}"))?;
    if resp.status() != 200 {
        return Err(anyhow!("HTTP {} для {url}", resp.status()));
    }
    let total: u64 = resp
        .header("content-length")
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);

    let mut reader = resp.into_reader();
    let mut file = fs::File::create(&tmp)?;
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    let mut done: u64 = 0;
    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])?;
        hasher.update(&buf[..n]);
        done += n as u64;
        if let Some(cb) = progress.as_deref_mut() {
            cb(done, total);
        }
    }
    file.flush()?;
    drop(file);

    if let Some(expected) = sha256 {
        let got = format!("{:x}", hasher.finalize());
        if got != expected.to_ascii_lowercase() {
            let _ = fs::remove_file(&tmp);
            return Err(anyhow!("SHA-256 не совпал для {url}"));
        }
    }
    fs::rename(&tmp, dest)?;
    Ok(dest.to_path_buf())
}

/// Скачать в память (для APK/JSON эндпоинтов).
pub fn get_bytes(url: &str) -> Result<Vec<u8>> {
    let resp = ureq::get(url)
        .set("User-Agent", "SoberX/1.0")
        .timeout(std::time::Duration::from_secs(120))
        .call()
        .with_context(|| format!("GET {url}"))?;
    let mut buf = Vec::new();
    resp.into_reader().read_to_end(&mut buf)?;
    Ok(buf)
}
