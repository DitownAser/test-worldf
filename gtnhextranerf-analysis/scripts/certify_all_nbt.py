#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GTNH Extra Nerf — выдача ВСЕХ сертификатов без запуска игры.
Прямо правит WorldSavedData "gtnhextranerf_progression" внутри level.dat.

Подходит для ЛЮБОЙ версии GTNH (2.9.0 и новее), т.к. не зависит от
CraftTweaker/скриптов. Требует Python 3.8+:  pip install nbtlib

Использование:
    python3 certify_all_nbt.py /path/to/saves/TestWorld/level.dat
    (мир должен быть ЗАКРЫТ!)

Что делает:
    certifiedTiers   -> steam,lv,mv,hv,ev,iv,luv,zpm,uv,uhv,uev,uiv,umv,uxv,max = 1b
    certificateEpochs -> все = 0L  (чтобы креативные предметы-сертификаты тоже были валидны)
"""
import sys, gzip, io

try:
    import nbtlib
    from nbtlib.tag import Compound, Byte, Long
except ImportError:
    sys.exit("Нужна библиотека nbtlib:  pip install nbtlib")

TIERS = ["steam", "lv", "mv", "hv", "ev", "iv", "luv", "zpm",
         "uv", "uhv", "uev", "uiv", "umv", "uxv", "max"]

def main(path):
    # level.dat = gzip NBT; корневой тег имеет имя ""
    with open(path, "rb") as f:
        head = f.read(2)
    opener = gzip.open if head == b"\x1f\x8b" else open
    nbt = nbtlib.load(path) if head != b"\x1f\x8b" else \
          nbtlib.File.parse(io.BytesIO(gzip.decompress(open(path, "rb").read())), gzipped=False)

    data = nbt.setdefault("Data", Compound())
    prog = data.setdefault("gtnhextranerf_progression", Compound())

    tiers_c = prog.setdefault("certifiedTiers", Compound())
    epochs_c = prog.setdefault("certificateEpochs", Compound())
    for t in TIERS:
        tiers_c[t] = Byte(1)
        epochs_c.setdefault(t, Long(0))

    # сохраняем в том же формате, что и читаем
    if head == b"\x1f\x8b":
        buf = io.BytesIO()
        nbt.write(buf, gzipped=False)
        with gzip.open(path, "wb") as f:
            f.write(buf.getvalue())
    else:
        nbt.save(path)

    print("OK: все %d тиры записаны в %s" % (len(TIERS), path))
    print("Запускайте мир — машины всех тиров будут разблокированы.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
