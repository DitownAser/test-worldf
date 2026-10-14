"""CLI SoberX: soberx <команда>. Работает без GUI — удобно для скриптов."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .apk import inspect_apk, installed_list
from .auth import AuthManager
from .install import Installer
from .settings import Settings, xdg_config_home


def _prog(stage: str, cur: int, tot: int) -> None:
    print(f"[{cur:>3}/{tot}] {stage}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("soberx", description="SoberX — Roblox на Linux + кастомные APK")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="вход через браузер")
    sub.add_parser("logout", help="выход")
    sub.add_parser("whoami", help="текущий аккаунт")

    sp = sub.add_parser("channel", help="выбрать канал")
    sp.add_argument("name", choices=["stable", "canary", "atchi", "legacy_avi"])

    sub.add_parser("update", help="установить/обновить Windows-клиент (wine)")

    sub.add_parser("run", help="запустить игру через Wine (главный путь, как в sober)") \
       .add_argument("--place", help="placeId сервера")
    sub.add_parser("login-wine",
                   help="вход через redirect на localhost:59251 (webview-цикл sober)")

    sa = sub.add_parser("apk", help="работа с APK")
    sg = sa.add_subparsers(dest="apkg", required=True)
    sg.add_parser("list", help="список установленных APK")
    sg.add_parser("official", help="скачать официальный APK")
    sg.add_parser("install", help="установить кастомный APK").add_argument("file", type=Path)
    sg.add_parser("check", help="проверить APK").add_argument("file", type=Path)

    sl = sub.add_parser("launch", help="запустить клиент")
    sl.add_argument("--place", help="placeId сервера")
    sl.add_argument("--apk-mode", action="store_true",
                    help="режим Android APK (управление клавиатурой через маппер)")

    si = sub.add_parser("input", help="управление в APK-режиме (тапы/свайпы вместо тача)")
    ig = si.add_subparsers(dest="icmd", required=True)
    ip = ig.add_parser("profile", help="профиль управления")
    ip.add_argument("--export", type=Path, help="сохранить профиль JSON")
    ip.add_argument("--import-gameloop", type=Path, help="импорт XML-конфига GameLoop")
    ip.add_argument("--set-file", type=Path, help="использовать файл профиля при запуске")
    ig.add_parser("list", help="показать текущий профиль")
    ifeed = ig.add_parser("feed", help="выполнить триггеры: soberx input feed w a space")
    ifeed.add_argument("triggers", nargs="+")
    ifeed.add_argument("--serial", help="adb-серийник устройства")
    ifeed.add_argument("--dev", default="/dev/input/event2", help="evdev-устройство в контейнере")
    return p


class App:
    """Контекст команд CLI: настройки, авторизация, инсталлятор."""

    def __init__(self):
        self.st = Settings.load()
        self.auth = AuthManager(xdg_config_home() / "soberx")
        self.inst = Installer(self.st, _prog)

    # ---------- авторизация ----------
    def cmd_login(self, args) -> int:
        self.auth.login_interactive(self.st.browser, print, lambda u: print("откройте:", u))
        print("вход выполнен")
        return 0

    def cmd_logout(self, args) -> int:
        self.auth.logout()
        print("выход")
        return 0

    def cmd_whoami(self, args) -> int:
        print(self.auth.whoami().get("name", "не авторизован"))
        return 0

    def cmd_channel(self, args) -> int:
        self.st.channel = args.name
        self.st.save()
        print("канал:", args.name)
        return 0

    # ---------- wine-цикл (как sober) ----------
    def cmd_update(self, args) -> int:
        from .wineclient import WineClient
        wc = WineClient(self.st, lambda s: print(s, file=sys.stderr))
        print("установлено в", wc.update())
        return 0

    def cmd_login_wine(self, args) -> int:
        from .wineclient import WineClient
        wc = WineClient(self.st, lambda s: print(s, file=sys.stderr))
        wc.login()
        print("вход выполнен:", self.st.username or "(имя недоступно)")
        return 0

    def cmd_run(self, args) -> int:
        from .wineclient import WineClient
        wc = WineClient(self.st, lambda s: print(s, file=sys.stderr))
        proc = wc.launch(args.place)
        print("Roblox запущен через Wine, pid", proc.pid)
        return 0

    # ---------- APK ----------
    def cmd_apk(self, args) -> int:
        if args.apkg == "list":
            for i in installed_list(self.st.apk_store_dir):
                print(f"{i.path.name}: pkg={i.package} ver={i.version_name} "
                      f"abi={','.join(i.abi)} valid={i.valid}")
        elif args.apkg == "official":
            print("готово:", self.inst.install_apk(None))
        elif args.apkg == "install":
            print("APK установлен:", self.inst.install_apk(args.file))
        elif args.apkg == "check":
            i = inspect_apk(args.file)
            print(f"pkg={i.package} ver={i.version_name} code={i.version_code} "
                  f"abi={i.abi} valid={i.valid} err={i.error}")
        return 0

    def cmd_launch(self, args) -> int:
        if args.apk_mode:
            self.st.input_mode = "apk-mapping"
        proc = self.inst.launch(args.place)
        print("запущено, pid", proc.pid)
        if self.st.input_mode == "apk-mapping":
            from .inputmap import load_profile
            prof = load_profile(None, xdg_config_home() / "soberx")
            print(f"APK-режим: управление клавиатурой через профиль «{prof.name}» "
                  f"({len(prof.mappings)} биндов). Правый клик/камера — через scrcpy.")
        return 0

    # ---------- профиль управления ----------
    def cmd_input(self, args) -> int:
        from .inputmap import InputMapper, AdbTouchBackend, ControlProfile, load_profile
        cfgdir = xdg_config_home() / "soberx"
        if args.icmd == "profile":
            if args.import_gameloop:
                prof = ControlProfile.from_gameloop_xml(args.import_gameloop)
                prof.save(cfgdir / "controls.json")
                print(f"импортировано {len(prof.mappings)} биндов из GameLoop XML -> controls.json")
            elif args.set_file:
                shutil.copyfile(args.set_file, cfgdir / "controls.json")
                print("профиль применён:", args.set_file)
            elif args.export:
                load_profile(None, cfgdir).save(args.export)
                print("экспортирован в", args.export)
            else:
                print("указан профиль:", (cfgdir / "controls.json").exists())
        elif args.icmd == "list":
            prof = load_profile(None, cfgdir)
            print(f"профиль: {prof.name}  экран {prof.screen_w}x{prof.screen_h}")
            for m in prof.mappings:
                arrow = f"->{m.swipe_to}" if m.swipe_to else ""
                print(f"  {m.trigger:<16} {m.action:<6} "
                      f"({m.target_x:.2f},{m.target_y:.2f}){arrow}  {m.label}")
        elif args.icmd == "feed":
            if not shutil.which("adb"):
                print("ошибка: не найден adb (установите android-tools / platform-tools)",
                      file=sys.stderr)
                return 2
            prof = load_profile(None, cfgdir)
            mapper = InputMapper(prof, AdbTouchBackend(serial=args.serial, dev=args.dev))
            for t in args.triggers:
                ok = mapper.apply_trigger(t)
                print(f"{t}: {'выполнено' if ok else 'нет бинда'}")
        return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    app = App()
    handler = getattr(app, f"cmd_{args.cmd.replace('-', '_')}")
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
