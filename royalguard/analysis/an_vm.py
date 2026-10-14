import re
s = open('/workspace/0024_inline_script_05438659.js').read()

i = s.find("while(!![])")
print("---DISPATCH AREA---")
print(s[max(0,i-500):i+700])
print()

print("---ALL SWITCHES---")
for mm in re.finditer(r'switch\((\w+)\)', s):
    print(mm.start(), '::', s[mm.start()-120:mm.start()+60].replace('\n',' '))
print()

for pat in ['DataView','getUint32','Uint8Array','fromCharCode']:
    print(pat, s.count(pat))
print()

for pat in ['debugger','Function(','WebGL','canvas','plugins','languages','webdriver','headless','Notification','RTCPeerConnection','screen','hardwareConcurrency','deviceMemory','timezone','Intl','Date.now','performance','Worker','localStorage','sessionStorage','indexedDB','fetch','XMLHttpRequest','WebSocket','sendBeacon','document.cookie','atob','btoa','crypto','navigator','window.top','outerWidth']:
    c = s.count(pat)
    if c: print(f"{pat}: {c}")
