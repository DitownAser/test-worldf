import struct

DT_NEEDED=1; DT_PLTRELSZ=2; DT_STRTAB=5; DT_SYMTAB=6; DT_RELA=7; DT_RELASZ=8
DT_RELAENT=9; DT_STRSZ=10; DT_SYMENT=11; DT_INIT=12; DT_FINI=13; DT_SONAME=14
DT_JMPREL=0x17; DT_RELACOUNT=0x6ffffff9; DT_GNU_HASH=0x6ffffef5
DT_FLAGS=30; DT_FLAGS_1=0x6ffffffb; DT_VERSYM=0x6ffffff0; DT_VERNEED=0x6ffffffe
DT_VERNEEDNUM=0x6fffffff; DT_INIT_ARRAY=0x19; DT_FINI_ARRAY=0x1a
DT_PREINIT_ARRAY=0x20; DT_TEXTREL=0x16; DT_DEBUG=0x15

def load(path):
    d = bytearray(open(path,'rb').read())
    e_phoff, = struct.unpack_from('<Q', d, 0x20)
    e_phentsize, = struct.unpack_from('<H', d, 0x36)
    e_phnum, = struct.unpack_from('<H', d, 0x38)
    ph=[]
    for i in range(e_phnum):
        o=e_phoff+i*e_phentsize
        t,fl,off,va,pa,fsz,msz,al = struct.unpack_from('<IIQQQQQQ', d, o)
        ph.append(dict(t=t,fl=fl,off=off,va=va,fsz=fsz,msz=msz,al=al,hdr=o))
    return d, ph

def v2o(ph, va):
    for p in ph:
        if p['t']==1 and p['va'] <= va < p['va']+p['fsz']:
            return p['off'] + (va - p['va'])
    return None

def dyn_entries(d, ph):
    dyn = next(p for p in ph if p['t']==2)
    o = dyn['off']; res={}
    while True:
        tag,val = struct.unpack_from('<QQ', d, o)
        if tag==0: break
        res.setdefault(tag, []).append(val)
        o+=16
    return res, dyn

def read_cstr(d, off):
    end = d.index(b'\0', off)
    return bytes(d[off:end])

def parse_symbols(d, ph):
    """Return list of symbol dicts. Count derived from GNU_HASH table."""
    de,_ = dyn_entries(d, ph)
    symtab_va = de[DT_SYMTAB][0]; strtab_va = de[DT_STRTAB][0]
    sym_off = v2o(ph, symtab_va); st_off = v2o(ph, strtab_va)
    nsym = 0
    if DT_GNU_HASH in de:
        h_off = v2o(ph, de[DT_GNU_HASH][0])
        nbuckets, symbol_offset, bloom_size, bloom_shift = struct.unpack_from('<IIII', d, h_off)
        wordsz = 8  # ELF64
        buckets_off = h_off + 16 + bloom_size*wordsz
        chain_off = buckets_off + nbuckets*4
        # walk every bucket's chain; last entry of a chain has bit0 set
        maxidx = symbol_offset - 1
        for b in range(nbuckets):
            start = struct.unpack_from('<I', d, buckets_off + b*4)[0]
            i = start
            while i and not (struct.unpack_from('<I', d, chain_off + i*4)[0] & 1):
                i += 1
            if i > maxidx:
                maxidx = i
        nsym = maxidx + 1
    syms=[]
    for i in range(nsym):
        b = sym_off + i*24
        if b+24 > len(d): break
        name,info,other,shndx,value,size = struct.unpack_from('<IBBHQQ', d, b)
        nm = read_cstr(d, st_off+name) if name < de[DT_STRSZ][0] else b''
        syms.append(dict(name=nm, info=info, other=other, shndx=shndx, value=value, size=size))
    return syms, de
