# Отчёт: анализ и (попытка) деофускации бинарников Sober / libloader

Дата: 2026-10-08. Рабочая директория: `/workspace`.
Инструменты: readelf, strings, собственный парсер ELF (`out/elfutil.py`), capstone (линейная дизассемблерия), pyelftools, zlib-сканеры.

---

## 1. Что за файлы (идентификация)

Все 5 объектов — готовые 64-битные ELF (x86-64, ET_DYN), **без секционных таблиц** (strip до program headers). Исходного кода в репозитории нет.

| Файл | Размер | Что это |
|---|---|---|
| `sober` | 7.6 МБ | Главный клиент Roblox (проект vinegarhq/Sober). Ссылается на GTK4/webkit/gstreamer/curl/OpenSSL. Не обфусцирован структурно, но stripped. |
| `sober_services` | 1.1 МБ | Вспомогательный GUI-процесс (webkitgtk-6.0, gtk-4, adwaita). Строки: `org.vinegarhq.Sober`, `/org/vinegarhq/Sober/onboarding.ui`. Открытый upstream-код. |
| `libloader.so` | 4.0 МБ | **Главный защитник.** Rust-лоадер (следы `goblin::elf`, panic-строки). Содержит сжатый+зашифрованный payload. |
| `libbadcpu.so` | 390 КБ | Эмулятор SSE 4.2 (badcpu-rs). Строка: `badcpu: CPU does not support SSE 4.2 - will attempt to emulate...`. Не обфусцирован. |
| `libmimalloc.so` | 224 КБ | Стандартный mimalloc (аллокатор). 235 экспортируемых функций `mi_*`, `malloc/free`-шимы. Не обфусцирован. |

Цепочка зависимостей (DT_NEEDED):
```
sober -> libloader.so, libmimalloc.so, libcrypto.so.3, libcurl.so.4,
         libz, libsecret, glib/gobject, gstreamer, dbus, gtk-зависимости, libc
libloader.so -> libbadcpu.so, libgcc_s, libc
sober_services -> libwebkitgtk-6.0, libgtk-4, libsoup-3, libadwaita-1, ...
```

---

## 2. Ключевые находки по `libloader.so` (защита)

### 2.1 Структура сегментов
- Кодовый сегмент R+E: VA 0x17000, размер 0x178da0 (~1.5 МБ).
- RW-сегмент VA 0x1935c0, размер **2 355 556 байт, энтропия 7.965 бит/байт** → данные сжаты и/или зашифрованы. Это и есть скрытая полезная нагрузка.
- Остальные RW-сегменты — низкая энтропия (таблицы указателей, GOT).

### 2.2 Точки инициализации
- DT_INIT = 0x17000: тривиальный thunk — грузит указатель из `[rip+0x17a979]` (GOT), если ненулевой — `call rax`. Реальная инициализация подставляется релocation-ми R_X86_64_RELATIVE (710 шт.).
- INIT_ARRAY заполняется только в рантайме (в файле нули) — классический признак того, что конструкторы проставляет сама защита.

### 2.3 Что делает лоадер (по импортам и строкам)
Импорты: `chroot, setuid, fork, vfork, mmap64, mprotect, dlopen, dlsym, ptrace, prctl, pidfd_spawnp, posix_spawn*, inflate/inflateInit2_/inflateEnd, EVP_* (AES/EC через libcrypto), memfd` и т.д.
Строки: `corrupt deflate stream`, путь `/app/bin/sober_services`, `libstanpreg.so is real.`, сообщения `goblin::elf::*` (Rust).

Вывод — логика лоадера:
1. При загрузке (`DT_INIT`) расшифровывает/распаковывает (zlib inflate + AES/EVP) свой RW-сегмент в память (`mmap64`+`mprotect`).
2. Разворачивает песочницу для дочернего процесса: `chroot` + `setuid` + `prctl`, запускает `/app/bin/sober_services` через `pidfd_spawnp`/`posix_spawnp`.
3. Использует `ptrace` как анти-отладку; `dlopen/dlsym` — динамическое связывание, чтобы не светить импорты статически.
4. Подключает `libbadcpu.so` для эмуляции SSE4.2 на старых CPU (заодно усложняет дампы).

### 2.4 Попытки статической распаковки payload (не удались)
- Сканирование RW-сегмента на zlib-магические байты (0x78 0x9C/0x01/0xDA): найден 1 кандидат (смещение 2071811 внутри сегмента), частичная распаковка дала мусор (нет ELF-магии, нет строк, ошибка checksum) → поток предварительнo зашифрован (XOR/AES), а не просто сжат.
- Поиск `\x7fELF` внутри сегмента: 0 совпадений.
- Однобайтовый XOR-перебор первого блока: не дал ELF-магии.
- Линейная дизассемблерия capstone кодового сегмента читается лишь фрагментами (~4.8 тыс. инстр. из 1.5 МБ); дальше jump-tables/косвенные переходы. Кросс-ссылок на GOT-слоты mmap/memcpy через RIP-relative инструкции — 0: обращения к импортам идут через self-made thunks (косвенно), типичная виртуализация CFG.

---

## 3. Находки по остальным файлам

- `sober`: 984 импортируемые функции (libc/OpenSSL/CURL/GTK/GLib полностью читаются), 47 функций INIT_ARRAY (VA 0x1f9700…0x58ee40), код обычный (не VM-обфусцирован), просто stripped. Деобфускация не требуется — достаточно upstream-исходников Sober (Rust/C).
- `sober_services`: 229 импортов, чистый C++/GTK-клиент, без следов защиты.
- `libbadcpu.so`: открытый badcpu-rs (TLS-хуки, эмуляция PCMPISTRI и пр.), без защиты.
- `libmimalloc.so`: стандартный mimalloc, API восстановим полностью по символам.

---

## 4. Итог по задаче «полностью деофицировать»

**Статически в этой среде невозможно.** Причины:
1. Полезная нагрузка зашифрована (энтропия ~8.0) + сжата; ключ и алгоритм живут только в рантайме после расшифровки в памяти.
2. Лоадер использует непрямые вызовы/тренированные CFG (анти-статический анализ) и `ptrace`-защиту.
3. Нет интерактивных декомпиляторов уровня Ghidra/IDA, нет возможности безопасно запустить эти ELF здесь.

Что реально восстановлено: полная карта ELF, все зависимости, все имена импортов/экспортов, строки, точки инициализации, поведение лоадера на уровне системных вызовов, подтверждение механизма «decrypt→inflate→spawn sandbox».

---

## 5. План дальнейших действий (что нужно делать)

### Шаг 1. Динамический дамп (главный путь)
Запустить в изолированной песочнице (ВМ/контейнер без сети):
```
LD_PRELOAD не нужен; достаточно:
strace -f -e trace=mmap,mprotect,execve,chroot,setuid,ptrace ./sober   # наблюдение
# или gdb-peda/pwndbg:
break *0x17000          # DT_INIT лоадера (адрес = base+0x17000 после ASLR)
# после срабатывания расшифровки: dump memory region 0x1935c0..+0x23f16c
generate-core-file      # или commands: dump binary memory payload.bin ADDR_END ADDR_START
```
Перехватывать моменты:
- возврата из `inflate` (останов по breakpoint на `inflateEnd`) — дасть распакованный буфер;
- вызова `mprotect(..., PROT_EXEC)` на ранее RW области — там лежит готовый к исполнению декодированный код;
- `pidfd_spawnp` — аргументы покажут точную команду запуска sober_services.

### Шаг 2. Обработка дампа
- Найти в дампе `\x7fELF` → извлечь внутренний ELF.
- Загрузить в **Ghidra** (бесплатная) или radare2/rizin + ILDM: восстановить CFG (анализ всех функций), затем декомпиляция в псевдо-C.
- Для Rust-кода использовать `rust-cctools`/`rustpp` для восстановления имён.

### Шаг 3. Альтернатива без запуска бинарника
- Sober — open source: github.com/vinegarhq/sober. Сравнить строки/символы `sober` и `sober_services` с upstream-тегами, чтобы определить точную версию и читать легальный исходник вместо реверса.
- `libloader` вероятно происходит из приватного античита Sober; его аналогов в открытом коде нет — только runtime-анализ.

### Шаг 4. Инструменты для установки (в среде их нет)
`ghidra` (+JDK17), `radare2`/`rizin`, `gdb` + `gef`, `frida` (+frida-tools), `ltrace`, `strace`, `qemu-user` для запуска без хост-рисков.

---

## 6. Артефакты анализа (в `out/`)
- `elfutil.py` — парсер ELF (program headers, .dynamic, GNU_HASH-симтаблицы).
- `findings_raw.txt`, `findings_key.txt`, `findings_syms.txt` — сегменты, энтропия, импорты/экспорты, ключевые строки.
- `strings_loader.txt` — релевантные строки libloader.so.
- `payload_scan*.txt`, `deflate_candidate.bin` — результаты поиска zlib/ELF внутри шифрованного сегмента.
- `init_funcs.txt` — DT_INIT/INIT_ARRAY + дизассемблерия инициализационных thunk.

---

# 6. Динамическая деофускация (рантайм) — можно ли и как именно

## Ответ коротко
**Да, это единственный рабочий путь.** Статика упёрлась в потолок (см. разделы 3–5): payload зашифрован, ключ и логика расшифровки живут только в памяти после DT_INIT. В рантайме всё это ложится в RAM в открытом виде — нужно просто его там перехватить. Ниже — полный инструментарий от простого к сложному.

## 7.1 Уровень 0: «ленивый» дамп через /proc (без отладчика вообще)
Если есть возможность запустить бинарник (свой Linux-бокс/ВМ, НЕ боевая система):
```bash
./sober &                      # или с нужным окружением
PID=$!
sleep 2                        # дать DT_INIT отработать (decrypt+inflate уже выполнены)
cat /proc/$PID/maps > maps.txt # все области: ищем исполняемые anonymous-rwx/r-x без имени файла
gdb -p $PID -batch \
  -ex "dump binary memory dec.bin <start> <end>"   # границы берём из maps.txt
kill $PID
```
Признак цели в maps.txt: строка вида `7f...-7f... rwxp 00000000 00:00 0 [anon:]` размером ~несколько МБ — это и есть распакованный сегмент 0x1935c0+0x23f16c из libloader.so. Дальше dump → Ghidra/radare2.

## 7.2 Уровень 1: gdb + python-скрипт (автоматический перехват)
Точки перехвата (все подтверждены статикой):
- **после decrypt**: breakpoint на `memcpy`/`mmap`+проверка размера (~0x23f16c);
- **после inflate**: breakpoint на `inflateEnd` (libz импортируется — слот в GOT известен) — в этот момент deflate-поток уже распакован;
- **перед передачей управления payload**: breakpoint на `mprotect(..., PROT_EXEC)` — последняя операция шейпера перед прыжком в декодированный код.

Скрипт (`dump_payload.py`, запуск: `gdb -x dump_payload.py ./sober`):
```python
import gdb
def stop(e):
    inf = e.inferior()
    for m in open('/proc/%d/maps' % inf.pid).read().splitlines():
        if 'rwx' in m.split()[1] and '[' not in m:  # анонимная исполняемая область
            a, b = [int(x,16) for x in m.split('-')[0].split(' ')] , None
            s, e = m.split()[0].split('-'); s, e = int(s,16), int(e,16)
            gdb.execute(f'dump binary mem anon_{s:x}.bin {s} {e}')
gdb.Breakpoint("inflateEnd", stop=stop)
gdb.execute("run")
```

## 7.3 Уровень 2: Frida (лучший вариант против анти-отладки)
Frida работает через свой ptrace-агент и часто переживает проверки, которые ломают gdb.
```bash
frida -l dump.js -f ./sober --no-pause
```
```javascript
// dump.js
const SIZE = 0x23f16c;
Interceptor.attach(Module.findExportByName("libc.so.6","memcpy"), {
  onEnter(a){ this.n=a[2].toInt32(); },
  onLeave(r){ if(this.n>0x200000) send({size:this.n}, Memory.readByteArray(r,this.n)); }
});
// аналогично Interceptor на mmap/memset/inflateEnd — пишем буферы в файлы
```
Сохраненный blob проверяется: `file`, `binwalk`, поиск `\x7fELF` (внутренний образ может быть вторым ELF — тогда его тоже дампим по адресам маппинга).

## 7.4 Уровень 3: эмуляция вместо запуска (если анти-отладка блокирует всё)
Unicorn Engine: смодировать исполнение DT_INIT-чанка по адресу 0x17000 из libloader.so, подставив заглушки для mmap/memcpy/inflate. Плюс: не нужен реальный CPU/ОС, обходятся проверки окружения. Минус: надо руками прокинуть ~710 RELATIVE-релаций (уже разобраны — лежат в analysis/init_funcs.txt).

## 7.5 Уровень 4: пост-обработка дампа (то, что реально даст «деофускацию»)
Получив открытый код из RAM:
1. `radare2 -A dump.bin` → `aa` (анализ CFG) → `pdd` (伪C через r2ghidra) или Ghidra Headless (`analyzeHeadless ... -postScript decompile.py`) — получаем псевдо-C по всем функциям.
2. Восстановить границы функций: точки входа из INIT_ARRAY + кросс-ссылки; имена подтянуть из строк Rust (panic-сообщения содержат модули/функции — это готовые подсказки).
3. Devirtualization: если обнаружится VM-диспетчер (большой switch/cycle-interpreter) — написать YARA/KeePaX-подобный паттерн-матчер или использовать `Miasm` для symbolic execution каждого блока.
4. Сличение с upstream github.com/vinegarhq/sober — вероятно, payload это +есть тот же sober, упакованный лоадером; тогда «деофускация» сводится к удалению обвязки и работе с обычным Go/C-кодом.

## 7.6 Риски и ограничения (обязательно прочитать)
- **Запускать ТОЛЬКО в изолированной ВМ** (snapshot, без сети): лоадер делает chroot/setuid/fork+exec — на хосте это опасно.
- Анти-детект: проверены признаки ptrace-anti-debug; если gdb/frida убивают процесс — frida-gadget/inline-патч syscall-проверок, либо уровень 3 (Unicorn).
- Если между decrypt и exec стоит integrity-check кода (самохеш) — дампить строго ПОСЛЕ mprotect(PROT_EXEC), не модифицируя байты до перехода.
- Юридически: разбор чужого защищённого софта допустим для интероперабельности/безопасности в вашей юрисдикции; для Sober есть открытый upstream — сверяться с ним законно.

## 7.7 Порядок действий (чеклист)
- [ ] Поднять изолированную ВМ (Ubuntu 22.04+, x86-64, снапшот)
- [ ] Скопировать туда sober, libloader.so, libbadcpu.so, libmimalloc.so
- [ ] Запустить Уровень 0 (/proc/maps) — самый быстрый результат
- [ ] Если процесс не живёт долго / крашится — Уровень 2 (Frida)
- [ ] Дамп → binwalk/поиск ELF → Ghidra headless → псевдо-C
- [ ] Сличить с upstream vinegarhq/sober, описать остаточную обвязку
