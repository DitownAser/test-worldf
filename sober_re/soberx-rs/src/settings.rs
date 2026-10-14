//! Настройки SoberX: JSON в XDG-конфиге + производные пути (аналог sober ~/.sober/<user>).

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    // общие
    pub username: String,
    pub token: String,
    pub channel: String, // stable | canary | atchi | legacy_avi
    pub discord_rpc: bool,
    pub browser: String,
    // графика/клиент
    pub gpu: String, // auto | intel | nvidia | amd
    pub use_winewayland: bool,
    pub fullscreen: bool,
    pub custom_fps: u32,
    pub oodle_disabled: bool,
    pub xmllog_enabled: bool,
    // кастомные APK
    pub apk_source: String, // official | custom
    pub custom_apk_path: String,
    // управление в APK-режиме
    pub input_mode: String,
    pub control_profile: String,
    // прочее
    pub last_version: String,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            username: String::new(),
            token: String::new(),
            channel: "stable".into(),
            discord_rpc: true,
            browser: "xdg-open".into(),
            gpu: "auto".into(),
            use_winewayland: false,
            fullscreen: false,
            custom_fps: 0,
            oodle_disabled: false,
            xmllog_enabled: false,
            apk_source: "official".into(),
            custom_apk_path: String::new(),
            input_mode: String::new(),
            control_profile: String::new(),
            last_version: String::new(),
        }
    }
}

pub fn xdg_config_home() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".config"))
}

pub fn xdg_data_home() -> PathBuf {
    std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".local").join("share"))
}

static CACHE: std::sync::OnceLock<std::sync::Mutex<Option<(std::time::SystemTime, Settings)>>> =
    std::sync::OnceLock::new();

impl Settings {
    pub fn settings_dir() -> PathBuf {
        xdg_config_home().join("soberx")
    }

    fn file() -> PathBuf {
        Self::settings_dir().join("settings.json")
    }

    /// Загрузка с кэшем по mtime файла: повторные чтения — из памяти.
    pub fn load() -> Self {
        let path = Self::file();
        let mtime = fs::metadata(&path).and_then(|m| m.modified()).ok();
        let cache = CACHE.get_or_init(Default::default);
        {
            let guard = cache.lock().unwrap();
            if let Some((t, s)) = guard.as_ref() {
                if Some(*t) == mtime {
                    return s.clone();
                }
            }
        }
        let loaded = match fs::read_to_string(&path) {
            Ok(s) => serde_json::from_str(&s).unwrap_or_default(),
            Err(_) => Self::default(),
        };
        if let Some(t) = mtime {
            *cache.lock().unwrap() = Some((t, loaded.clone()));
        }
        loaded
    }

    pub fn save(&self) -> anyhow::Result<()> {
        let dir = Self::settings_dir();
        fs::create_dir_all(&dir)?;
        let tmp = dir.join(format!("settings.tmp.{}", std::process::id()));
        fs::write(&tmp, serde_json::to_string_pretty(self)?)?;
        fs::rename(&tmp, Self::file())?;
        // обновить кэш
        if let Ok(t) = fs::metadata(Self::file()).map(|m| m.modified()) {
            if let Ok(t) = t {
                *CACHE.get_or_init(Default::default).lock().unwrap() = Some((t, self.clone()));
            }
        }
        Ok(())
    }

    // --- производные пути (как у sober: <data>/clients/<user>/...) ---
    pub fn data_dir(&self) -> PathBuf {
        xdg_data_home().join("soberx")
    }

    pub fn client_root(&self) -> PathBuf {
        let user = if self.username.is_empty() { "default" } else { &self.username };
        self.data_dir().join("clients").join(user)
    }

    pub fn versions_dir(&self) -> PathBuf {
        self.client_root().join("versions")
    }

    pub fn prefix_dir(&self) -> PathBuf {
        self.client_root().join("prefix")
    }

    pub fn apk_store_dir(&self) -> PathBuf {
        self.data_dir().join("apks")
    }
}
