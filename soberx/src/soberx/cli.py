"""CLI SoberX: soberx <команда>. Работает без GUI — удобно для скриптов."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import version as vermod
from .apk import inspect_apk, install_apk, installed_list
from .auth import AuthManager
from .install import Installer
from .settings import Settings, xdg_config_home


def main(argv=None) -> int:
    st = Settings.load()
    auth = AuthManager(xdg_config_home() / "soberx")
    p = argparse.ArgumentParser("soberx", description="SoberX — Roblox на Linux + кастомные APK")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="вход через браузер")
    sub.add_parser("logout", help="выход")
    sub.add_parser("whoami", help="текущий аккаунт")

    sp = sub.add_parser("channel", help="выбрать канал")
    sp.add_argument("name", choices=["stable", "canary", "atchi", "legacy_avi"])

    sub.add_parser("update", help="установить/обновить Windows-клиент (wine)")

    sa = sub.add_parser("apk", help="работа с APK")
    sg = sa.add_subparsers(dest="apkg", required=True)
    sg.add_parser("list", help="список установленных APK")
    sg.add_parser("official", help="скачать официальный APK")
    a_i = sg.add_parser("install", help="установить кастомный APK")
    a_i.add_argument("file", type=Path)
    a_c = sg.add_parser("check", help="проверить APK")
    a_c.add_argument("file", type=Path)

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
    il = ig.add_parser("list", help="показать текущий профиль")
    ifeed = ig.add_parser("feed", help="выполнить триггеры: soberx input feed w a space")
    ifeed.add_argument("triggers", nargs="+")
    ifeed.add_argument("--serial", help="adb-серийник устройства")
    ifeed.add_argument("--dev", default="/dev/input/event2", help="evdev-устройство в контейнере")

    args = p.parse_args(argv)

    def prog(stage, cur, tot):
        print(f"[{cur:>3}/{tot}] {stage}", file=sys.stderr)

    inst = Installer(st, prog)

    if args.cmd == "login":
        tok = auth.login_interactive(st.browser, print, lambda u: print("откройте:", u))
        print("вход выполнен")
    elif args.cmd == "logout":
        auth.logout(); print("выход")
    elif args.cmd == "whoami":
        u = auth.whoami()
        print(u.get("name", "не авторизован"))
    elif args.cmd == "channel":
        st.channel = args.name; st.save(); print("канал:", args.name)
    elif args.cmd == "update":
        d = inst.install_wine(); print("установлено в", d)
    elif args.cmd == "apk":
        if args.apkg == "list":
            for i in installed_list(st.apk_store_dir):
                print(f"{i.path.name}: pkg={i.package} ver={i.version_name} abi={','.join(i.abi)} valid={i.valid}")
        elif args.apkg == "official":
            f = inst.install_apk(None); print("готово:", f)
        elif args.apkg == "install":
            f = inst.install_apk(args.file); print("APK установлен:", f)
        elif args.apkg == "check":
            i = inspect_apk(args.file)
            print(f"pkg={i.package} ver={i.version_name} code={i.version_code} abi={i.abi} valid={i.valid} err={i.error}")
    elif args.cmd == "launch":
        if args.apk_mode:
            st.input_mode = "apk-mapping"
        proc = inst.launch(args.place)
        print("запущено, pid", proc.pid)
        if getattr(st, "input_mode", "") == "apk-mapping":
            from .inputmap import load_profile
            prof = load_profile(None, xdg_config_home() / "soberx")
            print(f"APK-режим: управление клавиатурой через профиль «{prof.name}» "
                  f"({len(prof.mappings)} биндов). Правый клик/камера — через scrcpy.")
    elif args.cmd == "input":
        from .inputmap import (AdbTouchBackend, ControlProfile, InputMapper,
                               load_profile)
        cfgdir = xdg_config_home() / "soberx"
        if args.icmd == "profile":
            if args.import_gameloop:
                prof = ControlProfile.from_gameloop_xml(args.import_gameloop)
                prof.save(cfgdir / "controls.json")
                print(f"импортировано {len(prof.mappings)} биндов из GameLoop XML -> controls.json")
            elif args.set_file:
                import shutil
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
                print(f"  {m.trigger:<16} {m.action:<6} ({m.target_x:.2f},{m.target_y:.2f}){arrow}  {m.label}")
        elif args.icmd == "feed":
            import shutil as _sh
            if not _sh.which("adb"):
                print("ошибка: не найден adb (установите android-tools / platform-tools)", file=sys.stderr)
                return 2
            prof = load_profile(None, cfgdir)
            mapper = InputMapper(prof, AdbTouchBackend(serial=args.serial, dev=args.dev))
            for t in args.triggers:
                ok = mapper.apply_trigger(t)
                print(f"{t}: {'выполнено' if ok else 'нет бинда'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
