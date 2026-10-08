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
        proc = inst.launch(args.place)
        print("запущено, pid", proc.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
