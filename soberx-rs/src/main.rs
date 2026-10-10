//! SoberX — Roblox-клиент для Linux, порт sober (vinegarhq) на Rust.
//! CLI: login/logout/whoami/channel/update/apk/run/input.

mod apk;
mod auth;
mod download;
mod fasthttp;
mod inputmap;
mod libredirect;
mod settings;
mod version;
mod versionfile;
mod wineclient;

use anyhow::Result;
use clap::{Parser, Subcommand};
use settings::Settings;
use std::path::PathBuf;
use wineclient::WineClient;

#[derive(Parser)]
#[command(name = "soberx", version, about = "SoberX — Roblox на Linux (порт sober)")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Вход через браузер (redirect на localhost:59251, как у sober)
    Login,
    /// Выход и удаление токена
    Logout,
    /// Кто я (проверка сессии)
    Whoami,
    /// Показать/сменить канал: stable | canary | atchi | legacy_avi
    Channel { name: Option<String> },
    /// Скачать Windows-клиент (exe+dll чанками) и настроить Wine
    Update,
    /// Запустить игру (wine + libredirect). -p placeId
    Run {
        #[arg(short, long)]
        place: Option<String>,
    },
    /// Кастомные APK Roblox
    Apk {
        #[command(subcommand)]
        sub: ApkCmd,
    },
    /// Управление в APK-режиме (клавиатура вместо тача)
    Input {
        #[command(subcommand)]
        sub: InputCmd,
    },
    /// Собрать libredirect.so вручную
    BuildRedirect,
}

#[derive(Subcommand)]
enum ApkCmd {
    /// Список установленных APK
    List,
    /// Установить кастомный APK (или официальный, если путь не указан)
    Install { path: Option<PathBuf> },
    /// Проверить APK без установки
    Check { path: PathBuf },
}

#[derive(Subcommand)]
enum InputCmd {
    /// Показать текущий профиль управления
    List,
    /// Профиль: экспорт/импорт/установка файла
    Profile {
        #[arg(long)]
        export: Option<PathBuf>,
        #[arg(long)]
        import_gameloop: Option<PathBuf>,
        #[arg(long)]
        set_file: Option<PathBuf>,
    },
    /// Отправить действие клавиши эмулятору через adb
    Feed {
        keys: Vec<String>,
        #[arg(short, long)]
        serial: Option<String>,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    let mut st = Settings::load();

    match cli.cmd {
        Cmd::Login => {
            let mut wc = WineClient { st: &mut st };
            wc.login()?;
        }
        Cmd::Logout => {
            auth::logout(&Settings::settings_dir());
            st.token.clear();
            st.username.clear();
            st.save()?;
            println!("выход выполнен");
        }
        Cmd::Whoami => {
            let token = if !st.token.is_empty() {
                st.token.clone()
            } else {
                auth::saved_cookie(&Settings::settings_dir()).unwrap_or_default()
            };
            if token.is_empty() {
                println!("не авторизован — выполните `soberx login`");
                return Ok(());
            }
            match auth::whoami(&token) {
                Some(j) => println!(
                    "{} (id {})",
                    j["name"].as_str().unwrap_or("?"),
                    j["id"].as_i64().unwrap_or(0)
                ),
                None => println!("токен сохранён, но сессия не проверяется (нет сети?)"),
            }
        }
        Cmd::Channel { name } => match name {
            None => println!("канал: {}", st.channel),
            Some(n) => {
                // проверка валидности канала запросом версии
                let v = version::channel_version(&n)?;
                st.channel = n.clone();
                st.save()?;
                println!("канал {n}: версия {v}");
            }
        },
        Cmd::Update => {
            let mut wc = WineClient { st: &mut st };
            let dst = wc.update()?;
            println!("клиент установлен: {}", dst.display());
        }
        Cmd::Run { place } => {
            let wc = WineClient { st: &mut st };
            let mut cmd = wc.launch(place.as_deref())?;
            let status = cmd.spawn()?.wait()?;
            println!("игра завершилась со статусом {status}");
        }
        Cmd::Apk { sub } => match sub {
            ApkCmd::List => {
                let items = apk::installed_list(&st.apk_store_dir());
                if items.is_empty() {
                    println!("нет установленных APK");
                }
                for i in items {
                    println!(
                        "{}  pkg={} ver={} abi={} valid={}",
                        i.path.display(),
                        i.package,
                        i.version_name,
                        i.abi.join(","),
                        i.valid
                    );
                }
            }
            ApkCmd::Install { path } => {
                let dst = wineclient::install_apk(&mut st, path.as_deref())?;
                println!("APK установлен: {}", dst.display());
            }
            ApkCmd::Check { path } => {
                let info = apk::inspect_apk(&path);
                println!(
                    "pkg={} ver={} code={} abi={:?} size={} valid={} err={}",
                    info.package,
                    info.version_name,
                    info.version_code,
                    info.abi,
                    info.size,
                    info.valid,
                    info.error
                );
            }
        },
        Cmd::Input { sub } => match sub {
            InputCmd::List => {
                let prof = load_profile(&st);
                println!("профиль: {} ({} биндов)", prof.name, prof.bindings.len());
                for (k, a) in &prof.bindings {
                    let desc = match a {
                        inputmap::Action::Tap { x, y } => format!("tap {x},{y}"),
                        inputmap::Action::Swipe(s) => {
                            format!("swipe {},{}->{},{}", s.x1, s.y1, s.x2, s.y2)
                        }
                    };
                    println!("  {k:<6} -> {desc}");
                }
            }
            InputCmd::Profile { export, import_gameloop, set_file } => {
                if let Some(p) = import_gameloop {
                    let prof = inputmap::Profile::import_gameloop(&p)?;
                    let out = Settings::settings_dir().join("controls.json");
                    prof.save(&out)?;
                    st.control_profile = out.display().to_string();
                    st.save()?;
                    println!("импортировано {} биндов из {}", prof.bindings.len(), p.display());
                }
                if let Some(p) = set_file {
                    let prof = inputmap::Profile::load(&p)?;
                    println!("профиль загружен: {} ({} биндов)", prof.name, prof.bindings.len());
                    st.control_profile = p.display().to_string();
                    st.save()?;
                }
                if let Some(p) = export {
                    load_profile(&st).save(&p)?;
                    println!("экспортирован в {}", p.display());
                }
            }
            InputCmd::Feed { keys, serial } => {
                let prof = load_profile(&st);
                for k in keys {
                    prof.feed_key(&k, serial.as_deref())?;
                    println!("отправлено: {k}");
                }
            }
        },
        Cmd::BuildRedirect => {
            match libredirect::ensure_libredirect(&st.data_dir().join("libredirect")) {
                Some(p) => println!("собрано: {}", p.display()),
                None => println!("gcc не найден — соберите libredirect.c вручную"),
            }
        }
    }
    Ok(())
}

fn load_profile(st: &Settings) -> inputmap::Profile {
    if !st.control_profile.is_empty() {
        if let Ok(p) = inputmap::Profile::load(std::path::Path::new(&st.control_profile)) {
            return p;
        }
    }
    inputmap::Profile::default()
}
