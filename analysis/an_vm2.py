import re, base64
s = open('/workspace/0024_inline_script_05438659.js').read()

# 1. bytecode fetch: find 'bC' PC increment / instruction read
m = re.search(r'let (c\w+|cm|cl)=.{0,120}?getUint16', s)
print("getUint16 ctx:")
i = s.find('getUint16')
for i in range(len(s)):
    pass
idx = s.find('DataView')
print(s[idx-200:idx+400])
print('='*60)

# how instructions are fetched inside dispatch loop
j = s.find('cc=function')
seg = s[j:j+400]
print("cc head:", seg[:350])
print('='*60)

# find where cc( is called with args -> fetch of opcode
for mm in re.finditer(r'\bcc\(', s):
    print('call cc at', mm.start(), ':', s[mm.start()-250:mm.start()+30].replace('\n',' ')[-280:])
    break
print('='*60)

# string decoder b8/b9 functions
k = s.find("function b9")
print(s[k:k+900])
print('='*60)

# debugger hits
for mm in re.finditer(r'debugger', s):
    print('debugger ctx:', s[mm.start()-150:mm.start()+150])
