import re, base64

ALPHABET = 'j97bAgvlctR4CXpNExDF53L0uTkK26y/m+Zo8na1SfiUGzsYHwMqOPrVJhWIeBdQ'
TABLE = {ord(c): i for i, c in enumerate(ALPHABET)}

def b7(s):
    n = len(s)
    pad = 2 if (n > 1 and s[-1] == '=' and s[-2] == '=') else (1 if (n > 0 and s[-1] == '=') else 0)
    outlen = (n * 3 >> 2) - pad
    out = bytearray(outlen)
    k = 0
    for i in range(0, n, 4):
        bu = TABLE.get(ord(s[i]), 0)
        bv = TABLE.get(ord(s[i+1]), 0) if i+1 < n else 0
        bw = TABLE.get(ord(s[i+2]), 0) if i+2 < n else 0
        bx = TABLE.get(ord(s[i+3]), 0) if i+3 < n else 0
        out[k] = (bu << 2 | bv >> 4) & 0xff; k += 1
        if k < outlen: out[k] = ((bv & 0xf) << 4 | bw >> 2) & 0xff; k += 1
        if k < outlen: out[k] = ((bw & 3) << 6 | bx) & 0xff; k += 1
    return bytes(out)

src = open('/workspace/0024_inline_script_05438659.js').read()

# extract q array strings
mq = re.search(r"let q=\[(.*?)\];var r=Uint8Array", src, re.S)
qs = re.findall(r"'([^']+)'", mq.group(1))
print('q parts:', len(qs), [len(x) for x in qs])
blob = b''.join(b7(x) for x in qs)
print('total bytes:', len(blob))
open('/workspace/analysis/vm_blob_q.bin', 'wb').write(blob)

mu = re.search(r"let u=\[(.*?)\];", src[413000:], re.S)  # u defined after? find properly
i = src.find("let u=['")
seg = src[i:]
mend = re.search(r"\];", seg)
us = re.findall(r"'([^']*)'", seg[:mend.start()+1])
ublob = b''.join(b7(x) for x in us)
print('u parts:', len(us), 'bytes:', len(ublob))
open('/workspace/analysis/vm_blob_u.bin', 'wb').write(ublob)

# entropy of blob
from collections import Counter
import math
c = Counter(blob)
H = -sum((v/len(blob))*math.log2(v/len(blob)) for v in c.values())
print('entropy q-blob bits/byte:', round(H, 3))

# look for structure: try interpreting as bytecode stream — check first bytes repeated patterns
print('head hex:', blob[:64].hex())
print('tail hex:', blob[-64:].hex())
