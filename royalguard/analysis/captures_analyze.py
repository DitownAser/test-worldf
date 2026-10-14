#!/usr/bin/env python3
"""Анализ нового CDP-дампа captures/ (2026-10-13).

Воспроизводит ключевые находки CAPTURES_FINDINGS.md:
  1) верификация PoW Royal-Guard (sha256(prefix:nonce), ведущие нули);
  2) инвентарь endpoints + таймлайн сетевой цепочки;
  3) структура pushToTalk: классы размеров, heartbeat-интервалы, сбросы seq;
  4) расшифровка JWT madium и тела ответов.

Запуск: python3 analysis/captures_analyze.py [path/to/captures]
"""
import base64
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

CAP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "captures"


def events():
    for line in open(CAP / "logs" / "traffic.jsonl", encoding="utf8"):
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def pow_check():
    """Найти POST DTOM с rg_pow_* и проверить sha256(prefix:nonce)."""
    for e in events():
        if e.get("type") != "REQUEST":
            continue
        pd = e["extra"].get("postData") or ""
        if "rg_pow_prefix=" not in pd:
            continue
        d = dict(kv.split("=", 1) for kv in pd.split("&"))
        prefix, nonce = d["rg_pow_prefix"], d["rg_pow_nonce"]
        h = hashlib.sha256(f"{prefix}:{nonce}".encode()).hexdigest()
        zeros = len(h) - len(h.lstrip("0"))
        print("[PoW] prefix=%s nonce=%s -> %s..." % (prefix, nonce, h[:16]))
        print("[PoW] ведущих нулей hex: %d (заявленная сложность diff=%s)" % (zeros, d.get("rg_pow_diff")))
        assert h.startswith("0000"), "PoW НЕ подтверждён!"
        print("[PoW] ПОДТВЕРЖДЁН: формат sha256('prefix:nonce'), ~%s хешей потребовалось" % nonce)
        return True
    print("[PoW] POST с rg_pow_* не найден")
    return False


def endpoints():
    c = Counter()
    for e in events():
        if e.get("type") == "REQUEST":
            x = e["extra"]
            c[(x.get("method"), x.get("url", "?").split("?")[0])] += 1
    print("\n[Endpoints] всего уникальных (метод, путь):", len(c))
    for (m, u), n in sorted(c.items(), key=lambda kv: -kv[1]):
        if "beacon.min.js" in u or "/_next/" in u:
            continue
        print("  %3d %-6s %s" % (n, m, u))


def ptt_analysis():
    rows = []
    for e in events():
        if e.get("type") != "REQUEST":
            continue
        x = e["extra"]
        if "pushToTalk" not in x.get("url", "") or not x.get("postData"):
            continue
        p = json.loads(x["postData"])
        rows.append((e["timestamp"], p["seq"], len(base64.b64decode(p["payload"])),
                     len(base64.b64decode(p.get("payload2", "")) or ""),
                     len(base64.b64decode(p["hmac"]))))
    print("\n[pushToTalk] пакетов:", len(rows))
    print("  размеры payload:", dict(Counter(r[2] for r in rows)))
    print("  размеры payload2:", dict(Counter(r[3] for r in rows)))
    print("  размеры hmac:", dict(Counter(r[4] for r in rows)))
    ts = [dt.datetime.fromisoformat(r[0].replace("Z", "+00:00")) for r in rows]
    gaps = [round((b - a).total_seconds(), 1) for a, b in zip(ts, ts[1:])]
    print("  интервалы между пакетами (сек):", gaps)
    resets = sum(1 for a, b in zip(rows, rows[1:]) if b[1] == 0 and a[1] != 0)
    print("  сбросов счётчика seq:", resets, "(синхронно с re-handshake YX)")


def jwt_dump():
    for e in events():
        if e.get("type") != "REQUEST":
            continue
        auth = (e["extra"].get("headers") or {}).get("Authorization", "")
        if auth.startswith("Bearer "):
            payload = auth.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
            iat = dt.datetime.fromtimestamp(claims["iat"], dt.timezone.utc)
            exp = dt.datetime.fromtimestamp(claims["exp"], dt.timezone.utc)
            print("\n[Madium JWT]", claims, "| iat:", iat, "exp:", exp)
            return


def responses():
    for f in sorted((CAP / "responses").glob("*.json")):
        print("\n[Response]", f.name, "->", f.read_text(encoding="utf8")[:200])


if __name__ == "__main__":
    pow_check()
    endpoints()
    ptt_analysis()
    jwt_dump()
    responses()
