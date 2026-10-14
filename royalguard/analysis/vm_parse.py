import re, struct

ALPHABET = 'j97bAgvlctR4CXpNExDF53L0uTkK26y/m+Zo8na1SfiUGzsYHwMqOPrVJhWIeBdQ'
TABLE = {ord(c): i for i, c in enumerate(ALPHABET)}

def b7(s):
    n = len(s)
    pad = 2 if (n > 1 and s[-1] == '=' and s[-2] == '=') else (1 if (n > 0 and s[-1] == '=') else 0)
    outlen = (n * 3 >> 2) - pad
    out = bytearray(outlen); k = 0
    for i in range(0, n, 4):
        def g(j): return TABLE.get(ord(s[j]), 0) if j < n else 0
        bu, bv, bw, bx = g(i), g(i+1), g(i+2), g(i+3)
        if k < outlen: out[k] = (bu << 2 | bv >> 4) & 0xff; k += 1
        if k < outlen: out[k] = ((bv & 0xf) << 4 | bw >> 2) & 0xff; k += 1
        if k < outlen: out[k] = ((bw & 3) << 6 | bx) & 0xff; k += 1
    return bytes(out)

class R:
    def __init__(self, data): self.d = data; self.p = 0
    def byte(self):
        v = self.d[self.p]; self.p += 1; return v
    def u32le(self):
        v = struct.unpack_from('<I', self.d, self.p)[0]; self.p += 4; return v
    def varint_raw(self):
        r = 0; s = 0
        while True:
            b = self.byte(); r |= (b & 0x7f) << s; s += 7
            if b < 0x80: break
        return r
    def varint(self):
        r = self.varint_raw()
        return (r >> 1) ^ -(r & 1)

src = open('/workspace/0024_inline_script_05438659.js').read()
i = src.find("let u=['", src.find("var r=Uint8Array"))
seg = src[i:]
m = re.search(r"'\];", seg)
us = re.findall(r"'([^']*)'", seg[:m.start()+2])
blob = b''.join(b7(x) for x in us)
print('blob len:', len(blob))

r = R(blob)
first = r.byte()
magic = r.u32le()
print('first byte:', first, 'magic raw:', hex(magic), 'decoded:', hex(magic ^ 0xbfc9ddfd))
a = r.varint(); b = r.varint()
print('varints a,b:', a, b)
print('pos:', r.p)
# dump next 64 bytes
print(blob[r.p:r.p+64].hex())
