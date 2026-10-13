import re
s = open('/workspace/0024_inline_script_05438659.js').read()

# how q and u are used (no q[ / u[ found) -> find bare references
for name in ['q', 'u']:
    for mm in re.finditer(r'[,;=( ]' + name + r'[,;\)\.\[]', s):
        ctx = s[mm.start():mm.start()+160].replace('\n',' ')
        print(name, '@', mm.start(), ':', ctx[:150])
print('='*60)

# find the base64-ish decoder: search for a 64-char string table or bit ops <<0x12 etc
i = s.find('<<0x12')
print(s[i-300:i+300] if i!=-1 else 'no <<0x12')
print('='*60)

# search for '%' 64 or &0x3f patterns near charCodeAt
for mm in re.finditer(r'charCodeAt', s):
    print('charCodeAt @', mm.start(), ':', s[mm.start()-150:mm.start()+150].replace('\n',' '))
    print('-'*40)
