"""Тесты APK-модуля: парсинг, валидация, извлечение .so без реального Roblox."""
import sys, zipfile, struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from soberx import apk


def make_fake_apk(p: Path, roblox=True):
    with zipfile.ZipFile(p, "w") as z:
        # AndroidManifest.xml — просто кладём zip-запись с текстом (парсер устойчив к мусору)
        pkg = b"com.roblox.client" if roblox else b"com.example.app"
        z.writestr("AndroidManifest.xml", pkg + b"\x00\x00ver 1.6.9999999.1934")
        if roblox:
            z.writestr("lib/arm64-v8a/libroblox.so", b"\x7fELF fake so")
            z.writestr("assets/ClientVersion.xml", b"<xml>v</xml>")
        z.writestr("classes.dex", b"dex\n035\x00junk")


def main():
    tmp = Path("/tmp/soberx_tests"); tmp.mkdir(exist_ok=True)
    ok = fail = 0
    def check(name, cond):
        nonlocal ok, fail
        print(("PASS " if cond else "FAIL ") + name)
        ok += 1 if cond else 0; fail += 0 if cond else 1

    good = tmp / "good.apk"; make_fake_apk(good, True)
    bad  = tmp / "bad.apk";  make_fake_apk(bad, False)
    notz = tmp / "notz.apk"; notz.write_bytes(b"hello")

    i = apk.inspect_apk(good)
    check("валидный APK распознан", i.valid and "roblox" in i.package)
    check("ABI определены", "arm64-v8a" in i.abi)
    check("версия из манифеста", i.version_name.startswith("1.6."))
    j = apk.inspect_apk(bad)
    check("не-Roblox отбракован", not j.valid and j.error)
    k = apk.inspect_apk(notz)
    check("не-zip отбракован", not k.valid)

    store = tmp / "store"
    dst = apk.install_apk(good, store)
    check("APK установлен в хранилище", dst.is_file())
    try:
        apk.install_apk(bad, store); check("битый APK отклонён", False)
    except ValueError:
        check("битый APK отклонён", True)

    libs = apk.extract_native_libs(good, tmp / "libs", "arm64-v8a")
    check("libroblox.so извлечён", any(l.name == "libroblox.so" for l in libs))
    lst = apk.installed_list(store)
    check("список APK работает", len(lst) >= 1)

    print(f"\nИТОГ: {ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
