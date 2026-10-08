#!/usr/bin/env python3
"""
gdb-скрипт для рантайм-дампа распакованного payload из libloader.so (sober).
Запуск в изолированной ВМ:   gdb -q -x analysis/dump_payload.py --args ./sober
Точки останова подтверждены статикой: inflateEnd (конец распаковки zlib),
mprotect (перевод в PROT_EXEC перед прыжком в декодированный код),
ptrace (анти-отладка — ставим success-only чтобы видеть срабатывания).
"""
import gdb, os

OUT = "runtime_dumps"
os.makedirs(OUT, exist_ok=True)
dumped = set()

def dump_anon_exec():
    """С дампа /proc/PID/maps выгружаем анонимные исполняемые/записываемые области."""
    pid = gdb.selected_inferior().pid
    with open("/proc/%d/maps" % pid) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2: continue
            perms = parts[1]
            name = parts[5].strip() if len(parts) > 5 else ""
            # цель: анонимная область >= 1 МБ с записью (rwx/rw-/r-x без файла)
            if name and not name.startswith("["): continue
            s, e = (int(x, 16) for x in parts[0].split("-"))
            if (e - s) < 0x100000: continue
            if "w" not in perms and "x" not in perms: continue
            if (s, e) in dumped: continue
            dumped.add((s, e))
            fn = "%s/anon_%x-%x.bin" % (OUT, s, e)
            try:
                gdb.execute("dump binary memory %s %#x %#x" % (fn, s, e))
                print("[+] dumped %s (%d bytes)" % (fn, e - s))
            except Exception as ex:
                print("[-] %s: %s" % (fn, ex))

class DumpBP(gdb.Breakpoint):
    def stop(self):
        print("[*] hit: %s" % self.location); dump_anon_exec(); return False

for sym in ("inflateEnd", "mprotect", "ptrace"):
    try:
        DumpBP(sym)
        print("[+] breakpoint on %s" % sym)
    except gdb.error as e:
        print("[!] %s: %s" % (sym, e))

gdb.execute("set pagination off")
gdb.execute("run")
print("[*] inferior exited; final dump:")
dump_anon_exec()
