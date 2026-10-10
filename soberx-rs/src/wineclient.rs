//! Игровой цикл точь-в-точь как sober (vinegarhq), на Rust:
//!
//! 1. читаем/скачиваем version-файл канала;
//! 2. скачиваем чанки клиента (RobloxPlayerBeta.exe + DLL) и qjs;
//! 3. ставим winetricks-зависимости в префикс;
//! 4. браузерный вход с redirect на http://localhost:59251/auth?ROBLOSECURITY=...;
//! 5. запуск wine RobloxPlayerBeta.exe с токеном (-t) и LD_PRELOAD libredirect.so.

use crate::settings::Settings;
use crate::version as ver;
use crate::versionfile::{read_version, write_version, VersionFile};
use anyhow::{anyhow, Context, Result};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

pub fn have(cmdname: &str) -> bool {
    which_ok(cmdname)
}

fn which_ok(cmdname: &str) -> bool {
    Command::new("which")
        .arg(cmdname)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

pub struct WineClient<'a> {
    pub st: &'a mut Settings,
}

impl<'a> WineClient<'a> {
    fn log(&self, msg: &str) {
        println!("[soberx] {msg}");
    }

    // ---------- версия / чанки ----------
    pub fn update(&mut self) -> Result<PathBuf> {
        let v = ver::channel_version(&self.st.channel)?;
        self.log(&format!("версия канала {}: {v}", self.st.channel));
        let vf = read_version(&Settings::settings_dir(), &self.st.channel)?;
        let storage = match &vf {
            Some(f) => f.chunk_storage.clone(),
            None => ver::chunk_storage_for(&v, &self.st.channel),
        };
        let dst = self.st.versions_dir().join(&v);
        fs::create_dir_all(&dst)?;
        let got = ver::download_client_chunks(&v, &storage, &dst);
        if !got.iter().any(|n| n == "RobloxPlayerBeta.exe") {
            // fallback: прямой URL установочного CDN
            let base = ver::setup_base_url(&v);
            crate::download::download(
                &format!("{base}/RobloxPlayerBeta.exe"),
                &dst.join("RobloxPlayerBeta.exe"),
                None,
                None,
            )
            .context("не удалось скачать RobloxPlayerBeta.exe")?;
        }
        if let Err(e) = ver::get_qjs(&v, &storage, &dst) {
            self.log(&format!("qjs пропущен: {e}"));
        }
        write_version(
            &Settings::settings_dir(),
            &VersionFile {
                channel_version: v.clone(),
                chunk_storage: storage,
                ..Default::default()
            },
            &self.st.channel,
        )?;
        self.st.last_version = v;
        self.st.save()?;
        self.ensure_prefix()?;
        self.log("клиент обновлён");
        Ok(dst)
    }

    // ---------- wine-префикс ----------
    pub fn ensure_prefix(&self) -> Result<()> {
        let prefix = self.st.prefix_dir();
        fs::create_dir_all(&prefix)?;
        if !have("wine") {
            return Err(anyhow!("wine не найден — установите wine (>=9): sudo pacman -S wine"));
        }
        let done_marker = prefix.join(".soberx-booted");
        if !done_marker.is_file() {
            self.log("wineboot --init");
            let status = Command::new("wineboot")
                .arg("--init")
                .env("WINEPREFIX", &prefix)
                .env("WINEDEBUG", "-all")
                .status()?;
            if !status.success() {
                return Err(anyhow!("wineboot завершился с ошибкой"));
            }
            if have("winetricks") {
                for dep in ["vcrun2022", "dxvk", "corefonts"] {
                    self.log(&format!("winetricks {dep}"));
                    let _ = Command::new("winetricks")
                        .args(["-q", dep])
                        .env("WINEPREFIX", &prefix)
                        .env("WINEDEBUG", "-all")
                        .status();
                }
            }
            fs::write(&done_marker, b"")?;
        }
        Ok(())
    }

    /// Токен из authinfo.json — тот же файл, что создаёт официальный Windows-клиент
    /// после browser-flow входа (находится в drive_c/users/<user>/AppData/Local/Roblox/Versions).
    pub fn token_from_authinfo(&self) -> Option<String> {
        let drive_c = self.st.prefix_dir().join("drive_c");
        let users = drive_c.join("users");
        let rd = fs::read_dir(&users).ok()?;
        for e in rd.flatten() {
            if !e.path().is_dir() {
                continue;
            }
            let local = e.path().join("LocalAppData").join("Roblox").join("Versions");
            let mut candidates: Vec<PathBuf> = vec![local.clone()];
            if let Ok(vd) = fs::read_dir(&local) {
                candidates.extend(vd.flatten().map(|f| f.path()));
            }
            for dir in candidates {
                let p = dir.join("authinfo.json");
                if let Ok(data) = fs::read_to_string(&p) {
                    if let Ok(j) = serde_json::from_str::<serde_json::Value>(&data) {
                        if let Some(t) = j["ROBLOSECURITY"].as_str() {
                            let t = t.trim();
                            if !t.is_empty() {
                                return Some(t.to_string());
                            }
                        }
                    }
                }
            }
        }
        None
    }

    /// Вход как у sober: браузерный flow с redirect на localhost:59251.
    /// Если клиент уже логинился внутри Wine (authinfo.json), токен берётся оттуда.
    pub fn login(&mut self) -> Result<String> {
        if let Some(tok) = self.token_from_authinfo() {
            self.log("токен найден в authinfo.json Wine-префикса");
            if let Some(name) = crate::auth::username_from_token(&tok) {
                self.st.username = name;
            }
            self.st.token = tok.clone();
            self.st.save()?;
            crate::auth::store_cookie(&Settings::settings_dir(), &tok)?;
            return Ok(tok);
        }
        let tok = crate::auth::login_interactive(&self.st.browser, &|s| self.log(s))?;
        if let Some(name) = crate::auth::username_from_token(&tok) {
            self.st.username = name;
        }
        self.st.token = tok.clone();
        self.st.save()?;
        crate::auth::store_cookie(&Settings::settings_dir(), &tok)?;
        self.log("вход выполнен");
        Ok(tok)
    }

    // ---------- запуск игры ----------
    pub fn launch(&self, place: Option<&str>) -> Result<Command> {
        let v = if self.st.last_version.is_empty() {
            read_version(&Settings::settings_dir(), &self.st.channel)?
                .map(|f| f.channel_version)
                .unwrap_or_default()
        } else {
            self.st.last_version.clone()
        };
        if v.is_empty() {
            return Err(anyhow!("клиент не установлен — выполните `soberx update`"));
        }
        let exe = self.st.versions_dir().join(&v).join("RobloxPlayerBeta.exe");
        if !exe.is_file() {
            return Err(anyhow!(
                "клиент {v} не найден ({}), выполните `soberx update`",
                exe.display()
            ));
        }
        let mut cmd = Command::new("wine");
        cmd.env("WINEPREFIX", self.st.prefix_dir());
        // libredirect через LD_PRELOAD — точный механизм sober против блокировок
        if let Some(so) = crate::libredirect::ensure_libredirect(&self.st.data_dir().join("libredirect")) {
            let prev = std::env::var("LD_PRELOAD").unwrap_or_default();
            let new = if prev.is_empty() {
                so.display().to_string()
            } else {
                format!("{}:{}", so.display(), prev)
            };
            cmd.env("LD_PRELOAD", new);
        }
        // токен: приоритет у authinfo.json внутри префикса (как у официального клиента),
        // затем сохранённый браузерный токен soberx
        let token = self
            .token_from_authinfo()
            .or_else(|| if self.st.token.is_empty() { None } else { Some(self.st.token.clone()) });
        if let Some(t) = token {
            cmd.arg(format!("-t{t}"));
        }
        if let Some(p) = place {
            cmd.arg(format!("-a{p}"));
        }
        if self.st.fullscreen {
            cmd.arg("-f");
        }
        if self.st.custom_fps > 0 {
            cmd.arg(format!("--fps={}", self.st.custom_fps));
        }
        if self.st.use_winewayland {
            cmd.arg("--renderer=D3D11");
        }
        cmd.arg(&exe);
        // токен в аргументах скрываем при печати
        self.log(&format!(
            "запуск: wine {}",
            exe.file_name().unwrap_or_default().to_string_lossy()
        ));
        Ok(cmd)
    }
}

/// Установка кастомного/официального APK: извлечение библиотек и ассетов
/// в versions/android-<ver> (порт install.py::install_apk).
pub fn install_apk(st: &mut Settings, apk_path: Option<&Path>) -> Result<PathBuf> {
    let store = st.apk_store_dir();
    let apk_file = match apk_path {
        None => {
            println!("[soberx] официальный APK…");
            crate::apk::download_official(&store)?
        }
        Some(p) => {
            println!("[soberx] валидация APK…");
            crate::apk::install_apk(p, &store)?
        }
    };
    let info = crate::apk::inspect_apk(&apk_file);
    let vtag = if !info.version_name.is_empty() {
        info.version_name.clone()
    } else {
        apk_file.file_stem().unwrap_or_default().to_string_lossy().to_string()
    };
    let dst = st.versions_dir().join(format!("android-{vtag}"));
    fs::create_dir_all(&dst)?;
    println!("[soberx] извлечение библиотек…");
    let abi = if info.abi.iter().any(|a| a == "arm64-v8a") {
        Some("arm64-v8a")
    } else {
        info.abi.first().map(|s| s.as_str())
    };
    crate::apk::extract_native_libs(&apk_file, &dst.join("lib"), abi)?;
    // ассеты (.xml/.bundle/.json) из архива
    let data = fs::read(&apk_file)?;
    let mut zf = zip::ZipArchive::new(std::io::Cursor::new(data))?;
    let names: Vec<String> = zf.file_names().map(|s| s.to_string()).collect();
    for n in names {
        if n.starts_with("assets/")
            && matches!(
                Path::new(&n).extension().and_then(|e| e.to_str()),
                Some("xml") | Some("bundle") | Some("json")
            )
        {
            let target = dst.join(&n);
            fs::create_dir_all(target.parent().unwrap())?;
            let mut f = zf.by_name(&n)?;
            let mut buf = Vec::new();
            std::io::Read::read_to_end(&mut f, &mut buf)?;
            fs::write(&target, buf)?;
        }
    }
    st.custom_apk_path = apk_file.display().to_string();
    st.apk_source = if apk_path.is_some() { "custom" } else { "official" }.into();
    st.last_version = vtag;
    st.save()?;
    println!("[soberx] готово");
    Ok(dst)
}
