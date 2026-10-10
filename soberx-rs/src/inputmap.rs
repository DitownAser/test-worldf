//! Маппинг клавиатура/мышь -> виртуальный тач для APK-режима (порт inputmap.py).
//! Профили JSON, экспорт/импорт GameLoop/LDPlayer XML, отправка через adb sendevent.

use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Swipe {
    pub x1: u32,
    pub y1: u32,
    pub x2: u32,
    pub y2: u32,
    #[serde(default = "default_duration")]
    pub duration_ms: u32,
}

fn default_duration() -> u32 {
    80
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Action {
    Tap { x: u32, y: u32 },
    Swipe(Swipe),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Profile {
    pub name: String,
    pub screen_width: u32,
    pub screen_height: u32,
    /// клавиша -> действие
    pub bindings: HashMap<String, Action>,
}

impl Default for Profile {
    /// Профиль по умолчанию под Roblox: WASD -> стик слева, пробел -> прыжок.
    fn default() -> Self {
        let mut b = HashMap::new();
        let stick = |x2: u32, y2: u32| {
            Action::Swipe(Swipe { x1: 150, y1: 600, x2, y2, duration_ms: 80 })
        };
        b.insert("w".to_string(), stick(150, 400)); // вверх
        b.insert("s".to_string(), stick(150, 800)); // вниз
        b.insert("a".to_string(), stick(50, 600));  // влево
        b.insert("d".to_string(), stick(250, 600)); // вправо
        b.insert("space".to_string(), Action::Tap { x: 900, y: 700 }); // прыжок
        Self {
            name: "roblox-default".into(),
            screen_width: 1080,
            screen_height: 1920,
            bindings: b,
        }
    }
}

impl Profile {
    pub fn load(path: &Path) -> Result<Self> {
        Ok(serde_json::from_str(&std::fs::read_to_string(path)?)?)
    }

    pub fn save(&self, path: &Path) -> Result<()> {
        if let Some(p) = path.parent() {
            std::fs::create_dir_all(p)?;
        }
        std::fs::write(path, serde_json::to_string_pretty(self)?)?;
        Ok(())
    }

    /// Импорт конфига GameLoop/LDPlayer (упрощённо: <Key code="W"><Touch .../></Key>)
    pub fn import_gameloop(xml_path: &Path) -> Result<Self> {
        let text = std::fs::read_to_string(xml_path)?;
        let mut prof = Profile::default();
        prof.name = "gameloop-import".into();
        prof.bindings.clear();
        // очень простой парсер: ищем пары key="X" ... touch x1,y1,x2,y2
        for cap in text.split("<").skip(1) {
            let mut tag = cap.split(">").next().unwrap_or("");
            if !tag.starts_with("Key") && !tag.starts_with("key") {
                continue; // пропускаем <config>, </config> и прочие теги
            }
            if let Some(rest) = tag.split_once(' ') {
                tag = rest.1;
            }
            let key = extract_attr(tag, "key")
                .or_else(|| extract_attr(tag, "KeyCode"))
                .map(|k| k.to_lowercase());
            if let Some(k) = key {
                if let (Some(x1), Some(y1), Some(x2), Some(y2)) = (
                    extract_attr(tag, "startX").and_then(|v| v.parse().ok()),
                    extract_attr(tag, "startY").and_then(|v| v.parse().ok()),
                    extract_attr(tag, "endX").and_then(|v| v.parse().ok()),
                    extract_attr(tag, "endY").and_then(|v| v.parse().ok()),
                ) {
                    prof.bindings.insert(
                        k,
                        Action::Swipe(Swipe { x1, y1, x2, y2, duration_ms: 80 }),
                    );
                } else if let (Some(x), Some(y)) = (
                    extract_attr(tag, "x").and_then(|v| v.parse().ok()),
                    extract_attr(tag, "y").and_then(|v| v.parse().ok()),
                ) {
                    prof.bindings.insert(k, Action::Tap { x, y });
                }
            }
        }
        if prof.bindings.is_empty() {
            return Err(anyhow!("в XML не найдено биндов"));
        }
        Ok(prof)
    }

    fn adb(adb_args: &[String], cmd: &str) {
        let mut c = Command::new("adb");
        c.args(adb_args);
        c.arg("shell").arg(cmd);
        let _ = c.output();
    }

    /// Выполнить действие через adb (input swipe / input tap).
    pub fn feed_action(&self, action: &Action, serial: Option<&str>) -> Result<()> {
        if !crate::wineclient::have("adb") {
            return Err(anyhow!("adb не найден — установите android-tools"));
        }
        let args: Vec<String> = match serial {
            Some(s) => vec!["-s".into(), s.into()],
            None => vec![],
        };
        match action {
            Action::Tap { x, y } => {
                Self::adb(&args, &format!("input tap {x} {y}"));
            }
            Action::Swipe(sw) => {
                Self::adb(
                    &args,
                    &format!(
                        "input swipe {} {} {} {} {}",
                        sw.x1, sw.y1, sw.x2, sw.y2, sw.duration_ms
                    ),
                );
            }
        }
        Ok(())
    }

    pub fn feed_key(&self, key: &str, serial: Option<&str>) -> Result<()> {
        let action = self
            .bindings
            .get(&key.to_lowercase())
            .ok_or_else(|| anyhow!("нет бинда для клавиши {key}"))?;
        self.feed_action(action, serial)
    }
}

fn extract_attr<'a>(tag: &'a str, name: &str) -> Option<&'a str> {
    // точное совпадение имени атрибута: перед name= должен быть пробел/начало строки
    let mut search = tag;
    while let Some(idx) = search.find(name) {
        let before_ok = idx == 0 || search.as_bytes()[idx - 1] == b' ';
        let after = &search[idx + name.len()..];
        if before_ok {
            if let Some(v) = after.strip_prefix("=\"") {
                return v.split('"').next();
            }
        }
        search = &search[idx + 1..];
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_profile_roundtrip() {
        let dir = std::env::temp_dir().join(format!("soberx-input-{}", std::process::id()));
        let p = Profile::default();
        let f = dir.join("controls.json");
        p.save(&f).unwrap();
        let back = Profile::load(&f).unwrap();
        assert_eq!(back.bindings.len(), 5);
        assert!(matches!(back.bindings["w"], Action::Swipe(_)));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn gameloop_import() {
        let dir = std::env::temp_dir().join(format!("soberx-gl-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let xml = r#"<config>
<Key key="W" startX="100" startY="500" endX="100" endY="300"/>
<Key key="E" x="800" y="200"/>
</config>"#;
        let f = dir.join("g.xml");
        std::fs::write(&f, xml).unwrap();
        let prof = Profile::import_gameloop(&f).unwrap();
        assert_eq!(prof.bindings.len(), 2);
        assert!(matches!(prof.bindings["w"], Action::Swipe(_)));
        assert!(matches!(prof.bindings["e"], Action::Tap { .. }));
        std::fs::remove_dir_all(&dir).ok();
    }
}
