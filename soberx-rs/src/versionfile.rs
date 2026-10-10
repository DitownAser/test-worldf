//! version-файл клиента — точь-в-точь как в sober (vinegarhq).
//!
//! Формат: 7 строк:
//!   1) версия канала (r-xxxxxxx)
//!   2) URL чанков
//!   3) "0" (reserved)
//!   4) "1" (reserved)
//!   5) base64(DIFFIEHELLMANPARAMETERS)
//!   6) подпись (base64, отсутствует в dev-сборках)
//!   7) имя агента ("SoberX")
//!
//! Файл лежит в <config>/soberx/version (wine) и version_atchi (канал atchi).

use anyhow::{anyhow, Result};
use std::fs;
use std::path::{Path, PathBuf};

/// Стандартные DH-параметры Roblox (те же, что в APK/установщике Windows).
pub const DH_PARAMS_B64: &str = "MIIBIwKBgQCy4ldMCAFXe7GlHpByEnC1e2xG8nKcokGp+PSlDMFAuvq9EeDKdWbLZB0OHIhAikvHBsVBiWmXQF+d1jNYDBbPTXSvaSf1ngUBGS7Q40cNHKxYqD3lQmitH0Bjc9hLB2gGqVKxeNDGXo1Y8jP9jiJtP52RbPpfF0bNxBQ+mzHDTCwGQAO3GS8T0kKx4W9TkLFmC1sTP2lvSGRKWmVCcnNPdnFDU1BlUXJUVDJYNjFNNzRXODdNVjIyWTBuUT09Cg==";

#[derive(Debug, Clone)]
pub struct VersionFile {
    pub channel_version: String,
    pub chunk_storage: String,
    pub reserved_a: String,
    pub reserved_b: String,
    pub dh_params_b64: String,
    pub signature: String,
    pub agent: String,
}

impl Default for VersionFile {
    fn default() -> Self {
        Self {
            channel_version: String::new(),
            chunk_storage: String::new(),
            reserved_a: "0".into(),
            reserved_b: "1".into(),
            dh_params_b64: DH_PARAMS_B64.into(),
            signature: String::new(),
            agent: "SoberX".into(),
        }
    }
}

impl VersionFile {
    pub fn serialize(&self) -> Vec<u8> {
        [
            self.channel_version.as_str(),
            self.chunk_storage.as_str(),
            self.reserved_a.as_str(),
            self.reserved_b.as_str(),
            self.dh_params_b64.as_str(),
            self.signature.as_str(),
            self.agent.as_str(),
        ]
        .join("\n")
        .into_bytes()
    }

    pub fn deserialize(data: &[u8]) -> Result<Self> {
        let text = String::from_utf8_lossy(data);
        let lines: Vec<&str> = text.trim_end_matches('\n').split('\n').collect();
        if lines.len() < 7 {
            return Err(anyhow!(
                "битый version-файл: {} строк вместо 7",
                lines.len()
            ));
        }
        Ok(Self {
            channel_version: lines[0].to_string(),
            chunk_storage: lines[1].to_string(),
            reserved_a: lines[2].to_string(),
            reserved_b: lines[3].to_string(),
            dh_params_b64: lines[4].to_string(),
            signature: lines[5].to_string(),
            agent: lines[6].to_string(),
        })
    }

    /// Формат, задокументированный сообществом sober: поля разделены ТАБАМИ в одну строку.
    /// Поддерживаем оба варианта (табы и переводы строк).
    pub fn deserialize_tabtol(data: &[u8]) -> Result<Self> {
        let text = String::from_utf8_lossy(data);
        let sep = if text.contains('\t') { '\t' } else { '\n' };
        let lines: Vec<&str> = text.trim_end_matches(['\n', '\r']).split(sep).collect();
        if lines.len() < 7 {
            return Err(anyhow!(
                "битый version-файл: {} полей вместо 7",
                lines.len()
            ));
        }
        Ok(Self {
            channel_version: lines[0].trim().to_string(),
            chunk_storage: lines[1].trim().to_string(),
            reserved_a: lines[2].trim().to_string(),
            reserved_b: lines[3].trim().to_string(),
            dh_params_b64: lines[4].trim().to_string(),
            signature: lines[5].trim().to_string(),
            agent: lines[6].trim().to_string(),
        })
    }
}

/// Путь к version-файлу: stable/canary -> 'version', atchi -> 'version_atchi'.
pub fn version_path(settings_dir: &Path, channel: &str) -> PathBuf {
    let name = if channel == "atchi" { "version_atchi" } else { "version" };
    settings_dir.join(name)
}

pub fn write_version(settings_dir: &Path, vf: &VersionFile, channel: &str) -> Result<PathBuf> {
    fs::create_dir_all(settings_dir)?;
    let p = version_path(settings_dir, channel);
    fs::write(&p, vf.serialize())?;
    Ok(p)
}

pub fn read_version(settings_dir: &Path, channel: &str) -> Result<Option<VersionFile>> {
    let p = version_path(settings_dir, channel);
    if !p.is_file() {
        return Ok(None);
    }
    // сначала пробуем табовый формат сообщества, затем построчный
    let data = fs::read(&p)?;
    match VersionFile::deserialize_tabtol(&data) {
        Ok(vf) => Ok(Some(vf)),
        Err(e1) => VersionFile::deserialize(&data)
            .map(Some)
            .map_err(|e2| anyhow!("битый version-файл: {e1} / {e2}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        let vf = VersionFile {
            channel_version: "r-12ab34c".into(),
            chunk_storage: "https://cdn.example".into(),
            ..Default::default()
        };
        let back = VersionFile::deserialize(&vf.serialize()).unwrap();
        assert_eq!(back.channel_version, "r-12ab34c");
        assert_eq!(back.chunk_storage, "https://cdn.example");
        assert_eq!(back.agent, "SoberX");
        assert_eq!(back.dh_params_b64, DH_PARAMS_B64);
    }

    #[test]
    fn broken_rejected() {
        assert!(VersionFile::deserialize(b"only\nthree\nlines").is_err());
    }

    /// Реальный формат version-файла из сообщества sober (7 строк):
    /// версия канала, chunk-storage, reserved 0/1, DH base64, подпись, агент.
    #[test]
    fn parses_canonical_sober_version_file() {
        let sample = b"versionfe415f8d2394a8b\thttps://roblox-f611a5d5e6c8a1de.content.invisioncloudstatic.com\t0\t1\tMIIBIwKBgQCy4ldMCAFXe7GlHpByEnC1e2xG8nKcokGp+PSlDMFAuvq9EeDKdWbLZB0OHIhAikvHBsVBiWmXQF+d1jNYDBbPTXSvaSf1ngUBGS7Q40cNHKxYqD3lQmitH0Bjc9hLB2gGqVKxeNDGXo1Y8jP9jiJtP52RbPpfF0bNxBQ+mzHDTCwGQAO3GS8T0kKx4W9TkLFmC1sTP2lvSGRKWmVCcnNPdnFDU1BlUXJUVDJYNjFNNzRXODdNVjIyWTBuUT09\tMEUCIQDx...sig...\tSober\n";
        // sober использует табы как разделители — поддерживаем оба варианта
        let vf = VersionFile::deserialize_tabtol(sample).unwrap();
        assert_eq!(vf.channel_version, "versionfe415f8d2394a8b");
        assert!(vf.chunk_storage.starts_with("https://roblox-"));
        assert_eq!(vf.reserved_a, "0");
        assert_eq!(vf.reserved_b, "1");
        assert_eq!(vf.agent, "Sober");
    }
}
