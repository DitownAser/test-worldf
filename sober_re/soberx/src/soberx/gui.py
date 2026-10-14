"""GUI SoberX на GTK4/libadwaita (как у sober_services). Без GTK запускается CLI."""
from __future__ import annotations

import threading
from pathlib import Path


def run_gui() -> int:
    import gi
    gi.require_version("Gtk", "4.0")
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw
        HAS_ADW = True
    except ValueError:
        HAS_ADW = False
    from gi.repository import Gtk, GLib

    from . import version as vermod
    from .apk import inspect_apk
    from .auth import AuthManager
    from .install import Installer
    from .settings import Settings, xdg_config_home, xdg_data_home

    st = Settings.load()
    auth = AuthManager(xdg_config_home() / "soberx")

    App = Adw.Application if HAS_ADW else Gtk.Application
    app = App(application_id="org.soberx.Client", flags=0)

    def make_window(a):
        W = Adw.ApplicationWindow if HAS_ADW else Gtk.Window
        win = W(application=a, default_width=900, default_height=650, title="SoberX")

        toast = (Adw.ToastOverlay() if HAS_ADW else None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12,
                      margin_bottom=12, margin_start=12, margin_end=12)
        if toast: toast.set_child(box); win.set_content(toast)
        else: win.set_child(box)

        def notify(msg):
            if toast: toast.add_toast(Adw.Toast(title=str(msg)))
            else: print(msg)

        # --- статус ---
        status = Gtk.Label(label="Не авторизован", xalign=0)
        lbl_ver = Gtk.Label(label="", xalign=0)
        box.append(status); box.append(lbl_ver)

        bar = Gtk.ProgressBar(hexpand=False)
        box.append(bar)

        row = Gtk.Box(spacing=8)
        btn_login = Gtk.Button(label="Войти")
        btn_update = Gtk.Button(label="Обновить клиент (Wine)")
        btn_launch = Gtk.Button(label="▶ Играть")
        row.append(btn_login); row.append(btn_update); row.append(btn_launch)
        box.append(row)

        # --- секция APK ---
        sep = Gtk.Separator(); box.append(sep)
        box.append(Gtk.Label(label="Кастомные APK", xalign=0))
        apk_row = Gtk.Box(spacing=8)
        btn_apk = Gtk.Button(label="Загрузить .apk…")
        btn_apk_off = Gtk.Button(label="Скачать официальный APK")
        apk_list = Gtk.ListBox()
        apk_row.append(btn_apk); apk_row.append(btn_apk_off)
        box.append(apk_row); box.append(apk_list)

        def refresh_apks(*_):
            for r in apk_list: apk_list.remove(r)
            for p in sorted(st.apk_store_dir.glob("*.apk")):
                i = inspect_apk(p)
                lab = Gtk.Label(label=f"{i.package} {i.version_name} [{','.join(i.abi)}]", xalign=0)
                rb = Gtk.CheckButton(label="", active=(st.custom_apk_path == str(p)))
                rb.connect("toggled", lambda b, path=p: select_apk(b, path))
                r = Gtk.ListBoxRow(); bb = Gtk.Box(spacing=6); bb.append(rb); bb.append(lab)
                r.set_child(bb); apk_list.append(r)

        def select_apk(b: Gtk.CheckButton, path: Path):
            if b.get_active():
                st.custom_apk_path = str(path); st.apk_source = "custom"
            else:
                st.custom_apk_path = ""
            st.save(); notify(f"выбран APK: {path.name}" if b.get_active() else "снята галка")

        def on_progress(stage, cur, tot):
            GLib.idle_add(lambda: (bar.set_fraction(cur / max(tot, 1)),
                                   lbl_ver.set_text(f"{stage}"), None)[-1])

        def worker(fn, *a):
            threading.Thread(target=lambda: _run(fn, *a), daemon=True).start()

        def _run(fn, *a):
            try:
                res = fn(*a)
                GLib.idle_add(lambda: notify(str(res)))
            except Exception as e:
                GLib.idle_add(lambda: notify(f"ошибка: {e}"))

        def do_login(*_):
            def f():
                tok = auth.login_interactive(st.browser,
                        lambda s: GLib.idle_add(status.set_text, s),
                        lambda u: GLib.idle_add(notify, f"Открылась ссылка входа: {u}"))
                who = auth.whoami()
                GLib.idle_add(status.set_text, f"Вы вошли: {who.get('name','?')}")
                return "вход выполнен"
            worker(f)

        def do_update(*_):
            # точь-в-точь цикл sober: version-файл -> чанки -> qjs -> wine-префикс
            from .wineclient import WineClient
            worker(lambda: WineClient(st, lambda s: GLib.idle_add(on_progress, s, 1, 1)).update())

        def do_launch(*_):
            # запуск Windows-клиента через wine + LD_PRELOAD libredirect (как у sober)
            from .wineclient import WineClient
            worker(lambda: f"pid {WineClient(st).launch().pid}")

        def file_dialog(title: str, filter_name: str, pattern: str, action_label: str):
            """Одноразовый FileChooserDialog с одним фильтром."""
            dlg = Gtk.FileChooserDialog(title=title, transient_for=win,
                                        action=Gtk.FileChooserAction.OPEN)
            flt = Gtk.FileFilter()
            flt.set_name(filter_name)
            flt.add_pattern(pattern)
            dlg.add_filter(flt)
            dlg.add_button("Отмена", Gtk.ResponseType.CANCEL)
            dlg.add_button(action_label, Gtk.ResponseType.OK)
            return dlg

        def do_apk_chooser(*_):
            dlg = file_dialog("Выберите APK", "Android APK", "*.apk", "Установить")

            def resp(d, r):
                if r == Gtk.ResponseType.OK:
                    fp = Path(d.get_filename())
                    worker(lambda: Installer(st, on_progress).install_apk(fp) and refresh_apks())
                dlg.destroy()
            dlg.connect("response", resp)
            dlg.present()

        def do_apk_official(*_):
            worker(lambda: Installer(st, on_progress).install_apk(None) and refresh_apks())

        # --- секция управления (APK-режим: WASD вместо тача) ---
        box.append(Gtk.Separator())
        box.append(Gtk.Label(label="Управление в APK-режиме", xalign=0))
        chk_kb = Gtk.CheckButton(label="Клавиатура/мышь вместо тач-управления (WASD)")
        chk_kb.set_active(getattr(st, "input_mode", "") == "apk-mapping")

        def toggle_kb(b):
            st.input_mode = "apk-mapping" if b.get_active() else ""
            st.save(); notify("включён маппинг клавиш->тапы" if b.get_active() else "маппинг выключен")
        chk_kb.connect("toggled", toggle_kb)
        box.append(chk_kb)

        kb_row = Gtk.Box(spacing=8)
        btn_kb_import = Gtk.Button(label="Импорт конфига GameLoop (.xml)")
        btn_kb_export = Gtk.Button(label="Экспорт профиля (.json)")
        kb_row.append(btn_kb_import); kb_row.append(btn_kb_export)
        box.append(kb_row)

        def do_kb_import(*_):
            dlg = file_dialog("Конфиг управления GameLoop", "GameLoop XML", "*.xml",
                              "Импортировать")

            def resp(d, r):
                if r == Gtk.ResponseType.OK:
                    from .inputmap import ControlProfile
                    prof = ControlProfile.from_gameloop_xml(Path(d.get_filename()))
                    prof.save(xdg_config_home() / "soberx" / "controls.json")
                    notify(f"импортировано биндов: {len(prof.mappings)}")
                dlg.destroy()
            dlg.connect("response", resp)
            dlg.present()

        def do_kb_export(*_):
            from .inputmap import load_profile
            p = xdg_data_home() / "soberx" / "controls.json"
            load_profile(None, xdg_config_home() / "soberx").save(p)
            notify(f"профиль сохранён: {p}")

        btn_kb_import.connect("clicked", do_kb_import)
        btn_kb_export.connect("clicked", do_kb_export)

        btn_login.connect("clicked", do_login)
        btn_update.connect("clicked", do_update)
        btn_launch.connect("clicked", do_launch)
        btn_apk.connect("clicked", do_apk_chooser)
        btn_apk_off.connect("clicked", do_apk_official)

        # первоначальный статус
        who = auth.whoami()
        if who: status.set_text(f"Вы вошли: {who.get('name','?')}")
        try:
            lbl_ver.set_text(f"Текущая версия Roblox: {vermod.current_version()}")
        except Exception:
            lbl_ver.set_text("нет сети — версия неизвестна")
        refresh_apks()
        return win

    app.connect("activate", make_window)
    return app.run(None)


def main() -> int:
    try:
        import gi  # noqa: F401
    except ImportError:
        from .cli import main as cli_main
        print("PyGObject/GTK недоступен — запускаю CLI. Пример: soberx --help")
        return cli_main(["whoami"])
    return run_gui()
