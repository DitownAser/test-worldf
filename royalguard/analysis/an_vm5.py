import re, base64

s = open('/workspace/0024_inline_script_05438659.js').read()

# 1) decode a b64 blob and analyze entropy / structure
m = re.findall(r"'([A-Za-z0-9+/]{120,}={0,2})'", s)
blob = base64.b64decode(m[0] + '=' * ((4 - len(m[0]) % 4) % 4))
print('decoded len:', len(blob))
from collections import Counter
c = Counter(blob)
print('distinct bytes:', len(c), 'top:', c.most_common(8))
print('first 48 hex:', blob[:48].hex())

# check repeated 4-byte pattern period (XOR key length guess via autocorrelation)
for period in range(1, 65):
    match = sum(1 for i in range(len(blob)-period) if blob[i] == blob[i+period])
    rate = match / (len(blob)-period)
    if rate > 0.06:
        print('autocorr period', period, round(rate, 3))

# 2) find how the q/u string arrays are converted to byte buffers (the loader)
i = s.find("var r=Uint8Array")
print('---LOADER AREA---')
print(s[i:i+1500])
