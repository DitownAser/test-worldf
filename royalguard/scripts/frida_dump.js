// Frida-дамп payload из libloader.so. Запуск в изолированной ВМ:
//   frida -l analysis/frida_dump.js -f ./sober
// Пишет все большие memcpy/mmap-области в /tmp/sober_dump/.
"use strict";
var OUT = "/tmp/sober_dump/";
function dumpBuf(p, n, tag) {
    if (n < 0x100000) return;              // только крупные (>1 МБ) — наш сегмент 0x23f16c
    try {
        var buf = p.readByteArray(n);
        // frida-tools сохраняют через send(); пишем и локально если есть File
        send({tag: tag, size: n}, buf);
        console.log("[+]", tag, n.toString(16));
    } catch (e) { console.log("[-]", e); }
}
var libc = Process.getModuleByName("libc.so.6");
["memcpy", "memmove"].forEach(function (f) {
    Interceptor.attach(libc.getExportByName(f), {
        onEnter: function (a) { this.d = a[0]; this.n = a[2].toInt32(); },
        onLeave: function () { dumpBuf(this.d, this.n, f); }
    });
});
Interceptor.attach(libc.getExportByName("mmap64"), {
    onLeave: function (rv) { if (!rv.isNull() && rv.toInt32 !== -1) this.sz = 0; }
});
// конец inflate => буфер источника больше не нужен, приёмник готов:
var zl = Module.findExportByName(null, "inflateEnd");
if (zl) Interceptor.attach(zl, { onEnter: function () { console.log("[*] inflateEnd"); } });
// перевод сегмента в exec — последняя возможность снять чистый дамп:
Interceptor.attach(libc.getExportByName("mprotect"), {
    onEnter: function (a) { this.a = a[0]; this.n = a[1].toInt32(); this.p = a[2].toInt32(); },
    onLeave: function () { if (this.p & 4 /*PROT_EXEC*/ && this.n > 0x100000) { console.log("[*] mprotect EXEC", this.a, this.n.toString(16)); Memory.scan(this.a, Math.min(this.n, 0x300000), "7f 45 4c 46", { onMatch: function (a) { console.log("[!!] ELF header at", a); }, onComplete: function () {} }); } }
});
console.log("[*] hooks installed");
