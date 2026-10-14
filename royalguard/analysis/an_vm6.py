import re
s = open('/workspace/0024_inline_script_05438659.js').read()

# Find the vmG entry function and the code that transforms b64 strings -> Uint8Array
i = s.find('const G=function')  # helper
# search for 'atob' usage? none. Search for charCodeAt / lookup table for base64
for pat in ['charCodeAt', 'indexOf(', 'lookup', '0x40', 'decode']:
    print(pat, s.count(pat))
print('='*60)

# find first occurrence of q[ or u[ usage after arrays defined
j = s.find("let u=[")
seg = s[j:j+200]
# find where variables q and u are consumed
for mm in re.finditer(r'\bq\[', s):
    print('q[ at', mm.start(), ':', s[mm.start()-120:mm.start()+120].replace('\n',' '))
    break
for mm in re.finditer(r'\bu\[', s):
    print('u[ at', mm.start(), ':', s[mm.start()-120:mm.start()+120].replace('\n',' '))
    break
print('='*60)

# vmG definition: const vmG=(function(){ ... }) — find its return call signature; entry at end: vmG(0x0,undefined,...,0xda,0x3b,0x9c)
k = s.rfind('(function(){return vmG(')
print('entry:', s[k:k+120])
# find 'return' inside vmG closure near start - locate function body params
m0 = s.find('const vmG=(function()')
print(s[m0:m0+400])
