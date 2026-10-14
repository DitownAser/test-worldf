import re
s = open('/workspace/0024_inline_script_05438659.js').read()

# find the fetch of cl/cm right before switch cases in main loop: look for pattern like 'let cl=bz[bC]' or getUint16-like reads
for pat in ['bz[bC]', 'by[', '_$kiuM6g', '_$B34bL1', '_$kMgMuH', '_$85eM30', '_$z7jdwJ', '_$jMKbqv', '_$x7Pe5G']:
    print(pat, s.count(pat))
print('='*50)
i = s.find('_$kiuM6g')
# show reader definitions
for mm in re.finditer(r"Symbol\['?\w*'?\]|_\$kiuM6g'\]", s):
    pass
j = s.find("['_$kiuM6g']=")
if j == -1:
    # maybe defined via computed property
    m = re.search(r"\[\w+\['_\$kiuM6g'\]\]|_\$kiuM6g[=:]", s)
    print('def search:', m)
# find all occurrences context of first defs
occ = [mm.start() for mm in re.finditer(r'_\$kiuM6g', s)]
print('occurrences:', len(occ))
for o in occ[:3]:
    print(s[o-200:o+100].replace('\n',' '))
    print('-'*40)
