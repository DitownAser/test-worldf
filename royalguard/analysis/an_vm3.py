import re
s = open('/workspace/0024_inline_script_05438659.js').read()

# find main dispatch loop (contains 'continue' and fetch of cl/cm)
i = s.find('if(cm<0x34){if(cc(cm,cn))')
print(s[i-2500:i+500])
