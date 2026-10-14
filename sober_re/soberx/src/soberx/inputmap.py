"""inputmap — замена «бесячего телефонного» управления в APK-режиме.

Проблема: Roblox APK (com.roblox.client) рассчитан на тачскрин и не имеет
встроенной поддержки клавиатуры/мыши. sober/SoberX решает это так же, как
это делают Android-эмуляторы (BlueStacks/GameLoop): маппинг событий
клавиатуры/мыши ПК -> сенсорные тапы/свайпы внутри экрана эмулятора.

Два бэкэнда:
  * adb shell sendevent  -- пишет сырые события evdev в /dev/input во
    встроенном контейнере Waydroid (работает без root хоста).
  * scrcpy --control-others ... нет; вместо этого scrcpy сам по себе умеет
    "computer control device": мышь->тач. Если scrcpy запущен, маппер
    использует его окно и отдельная эмуляция не нужна.

Плюс загрузчик конфигов управления в формате GameLoop XML (совместимость
с готовыми профилями для Roblox) и собственный простой JSON-профиль.
"""
from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# коды Linux input-event (linux/input.h)
EV_KEY = 0x01
EV_ABS = 0x03
EV_SYN = 0x00
ABS_MT_SLOT = 0x2f
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
BTN_TOUCH = 0x14a

KEYMAP_NAME = {  # имя keysym -> скан-код KEY_* (только нужные для игр)
    "w": 17, "a": 30, "s": 31, "d": 32,
    "space": 57, "shift": 42, "ctrl": 29, "alt": 56, "esc": 1, "enter": 28,
    "q": 16, "e": 18, "r": 19, "t": 20, "f": 33, "g": 34, "z": 44, "x": 45,
    "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "up": 103, "left": 105, "right": 106, "down": 108,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
}


@dataclass
class TouchPoint:
    x_norm: int          # 0..screen_w нормализованные координаты evdev
    y_norm: int
    id: int


@dataclass
class Mapping:
    """Один привязанный элемент управления."""
    trigger: str                 # 'w', 'mouse_left', 'drag:jump'...
    action: str                  # tap | swipe | hold | key
    target_x: float              # доля ширины экрана 0..1 (куда тапать)
    target_y: float              # доля высоты
    radius: float = 0.05         # радиус зоны тапа (для свайпов)
    swipe_to: tuple[float, float] | None = None  # конец свайпа (доли)
    label: str = ""


@dataclass
class ControlProfile:
    name: str = "roblox-default"
    screen_w: int = 1920
    screen_h: int = 1080
    mappings: list[Mapping] = field(default_factory=list)

    # ---------- загрузка профилей ----------
    @classmethod
    def from_json(cls, path: Path) -> "ControlProfile":
        d = json.loads(path.read_text())
        prof = cls(name=d.get("name", path.stem),
                   screen_w=d.get("screen_w", 1920),
                   screen_h=d.get("screen_h", 1080))
        for m in d.get("mappings", []):
            prof.mappings.append(Mapping(
                trigger=m["trigger"], action=m["action"],
                target_x=m["x"], target_y=m["y"],
                radius=m.get("radius", 0.05),
                swipe_to=tuple(m["swipe_to"]) if m.get("swipe_to") else None,
                label=m.get("label", "")))
        return prof

    @classmethod
    def from_gameloop_xml(cls, path: Path) -> "ControlProfile":
        """Импорт готовых конфигов GameLoop/LDPlayer (XML .keymapping)."""
        root = ET.parse(path).getroot()
        prof = cls(name=path.stem)
        for el in root.iter():
            tag = el.tag.lower()
            if tag in ("key", "keyboard", "button"):
                k = el.attrib.get("keycode") or el.attrib.get("keysym") or ""
                cx = el.attrib.get("cx") or el.attrib.get("x")
                cy = el.attrib.get("cy") or el.attrib.get("y")
                if not k or cx is None or cy is None:
                    continue
                w = int(el.attrib.get("width", prof.screen_w)) or prof.screen_w
                h = int(el.attrib.get("height", prof.screen_h)) or prof.screen_h
                try:
                    tx, ty = float(cx) / w, float(cy) / h
                except ValueError:
                    continue
                kind = "swipe" if el.attrib.get("type") == "swipe" else "tap"
                sw = None
                sx, sy = el.attrib.get("sx2"), el.attrib.get("sy2")
                if kind == "swipe":
                    if sx is not None and sy is not None:
                        try:
                            sw = (float(sx) / w, float(sy) / h)
                        except ValueError:
                            sw = None
                    if sw is None:  # направление из типа: forward/back/left/right
                        d = (el.attrib.get("direction") or "").lower()
                        center = (tx, ty)
                        off = {"forward": (0, -0.2), "up": (0, -0.2),
                               "back": (0, 0.2), "down": (0, 0.2),
                               "left": (-0.1, 0), "right": (0.1, 0)}.get(d)
                        if off:
                            sw = (center[0] + off[0], center[1] + off[1])
                        else:
                            sw = (tx, max(0.0, ty - 0.2))  # по умолчанию «вперёд»
                prof.mappings.append(Mapping(trigger=str(k).lower(),
                                             action=kind, target_x=tx, target_y=ty,
                                             swipe_to=sw,
                                             label=el.attrib.get("name", "")))
        return prof

    # ---------- профиль по умолчанию под Roblox ----------
    @classmethod
    def roblox_default(cls) -> "ControlProfile":
        p = cls()
        p.mappings = [
            # движение — классический виртуальный стик слева
            Mapping("w", "swipe", 0.12, 0.62, swipe_to=(0.12, 0.42), label="вперёд"),
            Mapping("s", "swipe", 0.12, 0.62, swipe_to=(0.12, 0.82), label="назад"),
            Mapping("a", "swipe", 0.12, 0.62, swipe_to=(0.02, 0.62), label="влево"),
            Mapping("d", "swipe", 0.12, 0.62, swipe_to=(0.22, 0.62), label="вправо"),
            Mapping("space", "tap", 0.90, 0.55, label="прыжок"),
            Mapping("mouse_left", "tap", 0.50, 0.50, label="действие/удар"),
            Mapping("mouse_right_hold", "swipe", 0.70, 0.50, swipe_to=None,
                    label="камера мышью"),
            Mapping("e", "tap", 0.90, 0.70, label="сесть/действие"),
        ]
        return p

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        d = {"name": self.name, "screen_w": self.screen_w, "screen_h": self.screen_h,
             "mappings": [{"trigger": m.trigger, "action": m.action,
                           "x": m.target_x, "y": m.target_y, "radius": m.radius,
                           "swipe_to": list(m.swipe_to) if m.swipe_to else None,
                           "label": m.label} for m in self.mappings]}
        path.write_text(json.dumps(d, indent=2, ensure_ascii=False))


class AdbTouchBackend:
    """Пишет тач-события в контейнер через `adb shell sendevent`."""

    def __init__(self, serial: str | None = None, dev: str = "/dev/input/event2"):
        self.serial = serial
        self.dev = dev
        self._slot_id = 0

    def _adb(self, *args: str) -> subprocess.CompletedProcess:
        cmd = ["adb"] + (["-s", self.serial] if self.serial else []) + ["shell"] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    def _ev(self, t: int, code: int, value: int) -> None:
        self._adb("sendevent", self.dev, str(t), str(code), str(value))

    def tap(self, x: int, y: int) -> None:
        self._ev(EV_ABS, ABS_MT_TRACKING_ID, self._slot_id)
        self._ev(EV_ABS, ABS_MT_POSITION_X, x)
        self._ev(EV_ABS, ABS_MT_POSITION_Y, y)
        self._ev(EV_KEY, BTN_TOUCH, 1)
        self._ev(EV_SYN, 0, 0)
        self._ev(EV_ABS, ABS_MT_TRACKING_ID, -1)
        self._ev(EV_KEY, BTN_TOUCH, 0)
        self._ev(EV_SYN, 0, 0)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, steps: int = 12) -> None:
        self._ev(EV_ABS, ABS_MT_TRACKING_ID, self._slot_id)
        self._ev(EV_ABS, ABS_MT_POSITION_X, x1)
        self._ev(EV_ABS, ABS_MT_POSITION_Y, y1)
        self._ev(EV_KEY, BTN_TOUCH, 1)
        self._ev(EV_SYN, 0, 0)
        for i in range(1, steps + 1):
            fx = int(x1 + (x2 - x1) * i / steps)
            fy = int(y1 + (y2 - y1) * i / steps)
            self._ev(EV_ABS, ABS_MT_POSITION_X, fx)
            self._ev(EV_ABS, ABS_MT_POSITION_Y, fy)
            self._ev(EV_SYN, 0, 0)
        self._ev(EV_ABS, ABS_MT_TRACKING_ID, -1)
        self._ev(EV_KEY, BTN_TOUCH, 0)
        self._ev(EV_SYN, 0, 0)


class InputMapper:
    """Связывает профиль управления с бэкэндом тача.

    На реальном десктопе перехват клавиш даёт hotkey-библиотека (pynput),
    но чтобы модуль работал без GUI и без зависимостей, здесь публичный
    API: map_key()/map_mouse()/apply_trigger() — их вызывает GUI или CLI
    `soberx input feed`.
    """

    def __init__(self, profile: ControlProfile, backend: AdbTouchBackend):
        self.profile = profile
        self.backend = backend

    def apply_trigger(self, trigger: str) -> bool:
        for m in self.profile.mappings:
            if m.trigger != trigger:
                continue
            w, h = self.profile.screen_w, self.profile.screen_h
            x, y = int(m.target_x * w), int(m.target_y * h)
            if m.action == "tap":
                self.backend.tap(x, y)
            elif m.action == "swipe" and m.swipe_to:
                self.backend.swipe(x, y, int(m.swipe_to[0] * w), int(m.swipe_to[1] * h))
            elif m.action == "hold":
                self.backend.tap(x, y)  # упрощённо
            else:
                continue
            return True
        return False


def load_profile(path: Path | None, settings_dir: Path) -> ControlProfile:
    """Приоритет: указанный файл > gamepad.xml из conf-dir > профиль по умолчанию."""
    if path and path.is_file():
        if path.suffix == ".json":
            return ControlProfile.from_json(path)
        if path.suffix == ".xml":
            return ControlProfile.from_gameloop_xml(path)
    auto = settings_dir / "controls.json"
    if auto.is_file():
        return ControlProfile.from_json(auto)
    return ControlProfile.roblox_default()
