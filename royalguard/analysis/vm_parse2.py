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
    def __init__(self, data, p=0): self.d = data; self.p = p
    def byte(self):
        v = self.d[self.p]; self.p += 1; return v
    def u16le(self):
        v = struct.unpack_from('<H', self.d, self.p)[0]; self.p += 2; return v
    def u32le(self):
        v = struct.unpack_from('<I', self.d, self.p)[0]; self.p += 4; return v
    def i32le(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v
    def f64le(self):
        v = struct.unpack_from('<d', self.d, self.p)[0]; self.p += 8; return v
    def varint_raw(self):
        r = 0; s = 0
        while True:
            b = self.byte(); r |= (b & 0x7f) << s; s += 7
            if b < 0x80: break
        return r
    def svarint(self):  # _$jMKbqv: >>>1 ^ -(v&1)
        r = self.varint_raw()
        return (r >> 1) ^ -(r & 1)
    def xorstr(self, fnidx, keybase):
        ln = self.svarint()
        if ln < 0: ln = -ln  # guard
        state = ((keybase ^ ((fnidx * 0x9e3779b1) & 0xffffffff)) & 0xffffffff) or 1
        out = bytearray()
        for _ in range(ln):
            state ^= (state << 13) & 0xffffffff; state &= 0xffffffff
            state ^= state >> 17
            state ^= (state << 5) & 0xffffffff; state &= 0xffffffff
            b = self.byte() ^ (state & 0xff)
            out.append(b)
        return bytes(out).decode('utf-8', 'replace')

TAGS = {0: 'null', 0xb: 'undefined', 7: 'false', 0xa: 'true', 8: 'sbyte', 9: 'int16',
        5: 'i32', 1: 'f64', 3: 'stringXor', 6: 'bigint', 2: 'regexp', 4: 'bytes'}

def read_const(r, fnidx, keybase, deep=False):
    tag = r.byte()
    if tag == 0: return None
    if tag == 0xb: return 'undefined'
    if tag == 7: return False
    if tag == 0xa: return True
    if tag == 8:
        v = r.byte(); return v - 256 if v > 127 else v
    if tag == 9:
        v = r.u16le(); return v - 65536 if v > 32767 else v
    if tag == 5: return r.i32le()
    if tag == 1: return r.f64le()
    if tag == 3: return r.xorstr(fnidx, keybase)
    if tag == 6: return 'BigInt(' + r.xorstr(fnidx, keybase) + ')'
    if tag == 2:
        a = r.xorstr(fnidx, keybase); b = r.xorstr(fnidx, keybase)
        return f'RegExp({a!r},{b!r})'
    if tag == 4:
        ln = r.svarint()
        r.p += ln
        return f'<bytes {ln}>'
    raise ValueError(f'bad tag {tag} at {r.p}')

src = open('/workspace/0024_inline_script_05438659.js').read()

def get_blob(varname):
    i = src.find(f"let {varname}=['", src.find("var r=Uint8Array") - 500000)
    if i == -1: i = src.find(f"let {varname}=[")
    seg = src[i:]
    m = re.search(r"'\];", seg)
    parts = re.findall(r"'([^']*)'", seg[:m.start()+2])
    return b''.join(b7(x) for x in parts)

ublob = get_blob('u')
print('container size:', len(ublob))

hdr = R(ublob)
count = hdr.byte()
magic = hdr.u32le() ^ 0xbfc9ddfd
fnbs = hdr.svarint(); ftnb = hdr.svarint()
print('functions:', count, 'magic:', hex(magic), 'bs,bt:', fnbs, ftnb)
bv = [(fnbs | 1) & 0xffffffff, (fnbs * 0x5964d009 + 0xbe6397e5) & 0xffffffff]

def slot(i):
    return (i * bv[0] + bv[1]) & 0xffffffff

# We don't know the exact slot mapping of metadata fields from JS obfuscated indices,
# so parse sequentially by flags presence order as in bb():
flags = magic
FIELDS = [
    (0x8,    'paramCount'),      # aQ
    (0x20000,'?20000'),          # b0
    (0x1000, '?1000 u32'),       # aR
    (0x40000,'?40000 u32'),      # aP
    (0x40,   'nameCount'),       # aL
    (0x1,    '?1 u32'),          # aO
    (0x200000,'?200000 u32'),    # aN
    (0x20,   '?20 u32'),         # aM
    (0x2000, '?2000 vi'),        # b1
    (0x100000,'?100000 vi'),     # aK
]
print('flag bits set:', [hex(v) for v, n in FIELDS if flags & v], 'extra:', hex(flags & ~sum(v for v,_ in FIELDS)))

# parse name pool first (needed for strings inside code)
pos = hdr.p
tmp = R(ublob, pos)
try:
    if flags & 0x40:
        nc = tmp.svarint()
        print('name pool count:', nc)
        names = []
        for i in range(nc):
            idx = tmp.svarint()
            ln = tmp.svarint()
            raw = ublob[tmp.p:tmp.p+max(ln,0)]
            # try XOR keystream with state seeded by idx*const
            st = ((0 ^ ((idx * 0x9e3779b1) & 0xffffffff)) & 0xffffffff) or 1
            out = bytearray()
            for b in raw:
                st ^= (st << 13) & 0xffffffff; st &= 0xffffffff
                st ^= st >> 17
                st ^= (st << 5) & 0xffffffff; st &= 0xffffffff
                out.append(b ^ (st & 0xff))
            s1 = bytes(out).decode('utf-8','replace')
            st2 = ((0 ^ ((idx * 0x9e3779b1) & 0xffffffff)) & 0xffffffff) or 1
            tmp.p += ln
            names.append((idx, s1[:60]))
        for n in names[:40]: print(n)
except Exception as e:
    print('name pool parse err:', e, 'at', tmp.p)
