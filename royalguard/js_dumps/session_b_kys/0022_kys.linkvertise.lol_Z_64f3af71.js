(function(){'use strict';var lsText=document.getElementById('ls-text');var lsDots=document.getElementById('ls-dots');var lsBar=document.getElementById('ls-bar');var lsPct=document.getElementById('ls-pct');var RL_KEY='lbs_rl';var nativeST=window.setTimeout.bind(window);var nativeCI=window.clearInterval.bind(window);var nowFn=(typeof performance!=='undefined'&&performance.now)?function(){return performance.now();}:function(){return Date.now();};var raf=(window.requestAnimationFrame&&window.requestAnimationFrame.bind(window))||function(cb){return nativeST(function(){cb(nowFn());},16);};var caf=(window.cancelAnimationFrame&&window.cancelAnimationFrame.bind(window))||function(id){};var overlayHidden=false;var overlayFailed=false;function forensics(tag){var stamp=-1;try{stamp=Math.round(nowFn());}catch(_){}
try{console.error('[LBS-F] '+tag+' t='+stamp+'ms'+stageSnapshot());}catch(_){}}
var bootInfo='';try{var navType='';try{var navEntries=performance.getEntriesByType('navigation');if(navEntries&&navEntries.length)navType=navEntries[0].type||'';}catch(_){}
var bootLog=[];try{bootLog=JSON.parse(window.sessionStorage.getItem('lbs_boots')||'[]');}catch(_){bootLog=[];}
if(bootLog.length>8)bootLog=bootLog.slice(-8);var nowBoot=Date.now();var prevAge=bootLog.length?Math.round((nowBoot-bootLog[bootLog.length-1])/1000):-1;bootLog.push(nowBoot);try{window.sessionStorage.setItem('lbs_boots',JSON.stringify(bootLog));}catch(_){}
bootInfo='BOOT#'+bootLog.length+(navType?'('+navType+')':'')+
(prevAge>=0?' prev:'+prevAge+'s':'');try{console.error('[LBS] boot '+bootInfo);}catch(_){}}catch(_){bootInfo='';}
function hideLoadingScreen(){try{forensics('hide');}catch(_){}
try{if(overlayHidden||overlayFailed)return;overlayHidden=true;try{storageDel(RL_KEY);}catch(_){}
try{setProgress(100);}catch(_){}
try{lsBar.className+=(lsBar.className.indexOf('done')===-1?' done':'');}catch(_){}
try{nativeCI(dotsTimer);}catch(_){try{clearInterval(dotsTimer);}catch(_){}}
try{lsDots.textContent='';}catch(_){}
var screen=null;try{screen=document.getElementById('loading-screen');}catch(_){}
if(screen){try{if(screen.classList)screen.classList.add('fade-out');else screen.className+=' fade-out';}catch(_){try{screen.style.display='none';}catch(_){}}}}catch(_){try{var s2=document.getElementById('loading-screen');if(s2)s2.style.display='none';}catch(_){}
overlayHidden=true;}}
function afterMs(ms,cb){var start=nowFn();var fired=false;function fire(){if(fired)return;fired=true;cb();}
nativeST(fire,ms);(function tick(){if(fired)return;if(nowFn()-start>=ms)fire();else raf(tick);})();}
var dots=0;var dotsTimer=setInterval(function(){dots=(dots+1)%4;lsDots.textContent=new Array(dots+1).join('.');},420);function setStatus(txt){lsText.textContent=txt;lsText.className+=(lsText.className.indexOf('active')===-1?' active':'');try{refreshVMTag();}catch(_){}}
var vmShort='···';function shortVM(u){try{var s=String(u||'').split('?')[0].split('#')[0];s=s.substring(s.lastIndexOf('/')+1);s=s.replace(/\.(txt|js|json)$/i,'');return s||'···';}catch(_){return'···';}}
function refreshVMTag(){var el=null;try{el=document.getElementById('ls-vm');}catch(_){}
if(el){try{el.textContent='VM VERSION: '+vmShort+(bootInfo?' · '+bootInfo:'');}
catch(_){}}}
function setProgress(pct){var clamped=Math.max(0,Math.min(100,pct));lsBar.style.width=clamped+'%';lsPct.textContent=Math.round(clamped)+'%';}
window.VMReport=function(stage){if(overlayHidden)return;if(stage==='connecting'){setStatus('Connecting to RTDL');setProgress(96);return;}
if(stage==='handshake'){setStatus('Handshake done');setProgress(98);return;}
if(stage==='config'){setStatus('Opening content');setProgress(99);return;}
if(stage==='ready'){hideLoadingScreen();return;}
if(stage==='error'){if(overlayFailed)return;setFailed('Could not reach the server. Use Refresh page safely.');}};function visibleState(){var state={o3:false,frames:false,overlay:false,expanded:false,maxW:0};try{state.o3=(window._o3===true);}catch(_){}
var frames=[];try{frames=document.querySelectorAll('iframe');}catch(_){frames=[];}
try{state.frames=frames.length>0;for(var i=0;i<frames.length;i++){var rect=null;try{rect=frames[i].getBoundingClientRect();}catch(_){rect=null;}
var w=rect?rect.width:0;if(w>state.maxW){try{state.maxW=Math.floor(w);}catch(_){}}
if(rect&&rect.width>50&&rect.height>50)state.expanded=true;}}catch(_){}
try{state.overlay=!!document.getElementById('rg-overlay');}catch(_){}
return state;}
function stageSnapshot(){var snap=' [o3:0 ifr:0 ovl:0 mw:0]';try{var state=visibleState();snap=' [o3:'+(state.o3?1:0)+
' ifr:'+(state.frames?document.querySelectorAll('iframe').length:0)+
' ovl:'+(state.overlay?1:0)+
' mw:'+state.maxW+']';}catch(_){}
return snap;}
function setFailed(txt){try{forensics('fail: '+txt.split('[')[0]);}catch(_){}
overlayFailed=true;clearInterval(dotsTimer);lsDots.textContent='';setStatus(txt);lsBar.style.background='#ef4444';lsBar.style.webkitAnimation='none';lsBar.style.animation='none';}
function storageGet(k){try{return window.sessionStorage.getItem(k);}catch(e){return null;}}
function storageSet(k,v){try{window.sessionStorage.setItem(k,v);}catch(e){}}
function storageDel(k){try{window.sessionStorage.removeItem(k);}catch(e){}}
function cacheBust(){try{if(typeof crypto!=='undefined'&&typeof crypto.randomUUID==='function'){return crypto.randomUUID();}
if(typeof crypto!=='undefined'&&typeof crypto.getRandomValues==='function'){var b=new Uint8Array(16);crypto.getRandomValues(b);b[6]=(b[6]&0x0f)|0x40;b[8]=(b[8]&0x3f)|0x80;var hex=[];for(var i=0;i<16;i++)hex.push((b[i]<16?'0':'')+b[i].toString(16));var h=hex.join('');return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);}}catch(e){}
return String(Date.now())+'-'+String(Math.random()).slice(2);}
function queryParam(name){try{if(typeof URLSearchParams!=='undefined'){return new URLSearchParams(location.search).get(name);}}catch(e){}
var m=location.search.match(new RegExp('[?&]'+name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'=([^&]*)'));return m?decodeURIComponent(m[1].replace(/\+/g,' ')):null;}
function simulateTo(ceiling,from,durationMs){var start=nowFn();var handle;(function tick(now){var t=Math.min(1,((now||start)-start)/durationMs);var eased=1-Math.pow(1-t,3);setProgress(from+(ceiling-from)*eased);if(t<1)handle=raf(tick);})();return function(){caf(handle);};}
function concatBytes(chunks){var total=0;var i,c;for(i=0;i<chunks.length;i++){c=chunks[i];total+=c.byteLength||c.length||0;}
var out=new Uint8Array(total);var off=0;for(i=0;i<chunks.length;i++){c=chunks[i];out.set(c instanceof Uint8Array?c:new Uint8Array(c),off);off+=c.byteLength||c.length||0;}
return out;}
function bytesToString(u8){if(typeof TextDecoder!=='undefined'){return new TextDecoder('utf-8').decode(u8);}
var s='';var step=8192;for(var i=0;i<u8.length;i+=step){var slice=u8.subarray(i,i+step);s+=String.fromCharCode.apply(null,slice);}
try{return decodeURIComponent(escape(s));}catch(e){return s;}}
function blobToText(blob){if(blob&&typeof blob.text==='function')return blob.text();return new Promise(function(resolve,reject){var r=new FileReader();r.onload=function(){resolve(r.result);};r.onerror=function(){reject(r.error||new Error('FileReader'));};r.readAsText(blob);});}
function decodeChunks(chunks){try{return bytesToString(concatBytes(chunks));}catch(e){return blobToText(new Blob(chunks));}}
function fetchCompat(url,opts){return fetch(url,opts).catch(function(err){if(opts&&opts.cache){var retry={};for(var k in opts){if(Object.prototype.hasOwnProperty.call(opts,k)&&k!=='cache')retry[k]=opts[k];}
return fetch(url,retry);}
throw err;});}
function fetchText(url,opts,fromPct,toPct){return fetchCompat(url,opts).then(function(res){if(!res.ok)throw new Error('HTTP '+res.status);var len=Number(res.headers.get('Content-Length'))||0;var canStream=false;try{canStream=!!(res.body&&typeof res.body.getReader==='function'&&len);}catch(e){}
function viaText(){var stop=simulateTo(toPct,fromPct,1800);return res.text().then(function(text){stop();setProgress(toPct);return text;}).catch(function(){return fetchCompat(url,opts).then(function(retry){return retry.text();}).then(function(text){stop();setProgress(toPct);return text;});});}
if(!canStream)return viaText();var reader;try{reader=res.body.getReader();}catch(e){return viaText();}
var chunks=[];var received=0;function pump(){return reader.read().then(function(result){if(result.done)return decodeChunks(chunks);var chunk=result.value;chunks.push(chunk);received+=(chunk&&(chunk.byteLength||chunk.length))||0;setProgress(fromPct+Math.min(1,received/len)*(toPct-fromPct));return pump();});}
return pump().catch(function(){var stop=simulateTo(toPct,fromPct,1800);return fetchCompat(url,opts).then(function(retry){return retry.text();}).then(function(text){stop();setProgress(toPct);return text;});});});}
function expandSid(){var data=queryParam('data');var sid=queryParam('s');if(data||!sid)return Promise.resolve();return fetchCompat('/vm/q?s='+encodeURIComponent(sid),{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('vm-ticket '+r.status);return r.text();}).then(function(qs){if(qs&&qs.charAt(0)==='?'){try{history.replaceState(null,'','/vm/Z'+qs);}catch(e){location.replace('/vm/Z'+qs);return new Promise(function(){});}}});}
function runGlobalScript(code){try{(0,eval)(code);return true;}catch(e1){console.error('[LBS] eval failed',e1);try{var s=document.createElement('script');s.type='text/javascript';s.text=code;(document.head||document.getElementsByTagName('head')[0]||document.documentElement).appendChild(s);return true;}catch(e2){console.error('[LBS] script inject failed',e2);throw e2;}}}
function loadVMScript(){if(typeof fetch!=='function'||typeof Promise==='undefined'){setFailed('Update your browser to continue');return;}
setStatus('Requesting file token');setProgress(6);expandSid().then(function(){return fetchCompat('/api/v1/securityFileID?v='+cacheBust(),{cache:'no-store'});}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);setProgress(20);return r.json();}).then(function(json){var VM_Version=json&&json.VM_Version;if(!VM_Version)throw new Error('missing VM_Version');try{vmShort=shortVM(VM_Version);refreshVMTag();}catch(_){}
setStatus('Downloading VM Files');return fetchText(VM_Version,{cache:'force-cache'},24,94);}).then(function(code){setStatus('Running VM');setProgress(95);try{nativeST(function(){if(overlayHidden||overlayFailed)return;var snap='';try{snap=stageSnapshot();}catch(_){}
try{console.error('[LBS] still waiting for VM stage '+snap);}catch(_){}
try{setFailed('This is taking too long (possible network issue). Use Refresh page safely.'+snap);}catch(_){}},45000);}catch(_){}
try{runGlobalScript(code);}catch(eRun){try{console.error('[LBS] run failed',eRun);}catch(_){}}}).catch(function(e){console.error('[LBS] load failed',e);var reloads=parseInt(storageGet(RL_KEY)||'0',10)||0;if(reloads>=3){setFailed('This browser may not be supported. Our VM failed to initialize its WebAssembly modules. Try disabling browser extensions that may be causing the issue. Reloading in 5 seconds...');setTimeout(()=>{location.href=window.o1},5000)
return;}
storageSet(RL_KEY,String(reloads+1));setFailed('Connection failed, refreshing');nativeST(function(){location.reload();},2200);});}
loadVMScript();try{var lsNode=document.getElementById('loading-screen');if(lsNode&&window.MutationObserver){var seenFade=false;new MutationObserver(function(mutations){var cls='';try{cls=lsNode.className||'';}catch(_){}
var hasFade=(''+cls).indexOf('fade-out')!==-1;var hiddenByStyle=false;try{hiddenByStyle=!!(lsNode.style&&lsNode.style.display==='none');}catch(_){}
if(hasFade)seenFade=true;for(var i=0;i<mutations.length;i++){var mutation=mutations[i];try{console.error('[LBS-F] mut '+mutation.type+'.'+mutation.attributeName+' clase=['+cls+']');}catch(_){}}
if(overlayHidden&&!overlayFailed&&seenFade&&!hasFade&&!hiddenByStyle){try{console.error('[LBS-F] fade-out REMOVIDO por externo, re-escondiendo');}catch(_){}
try{try{lsNode.style.removeProperty('opacity');}catch(_){}
try{lsNode.style.removeProperty('visibility');}catch(_){}
try{lsNode.style.removeProperty('display');}catch(_){}
if(lsNode.classList)lsNode.classList.add('fade-out');else lsNode.className+=' fade-out';}catch(_){try{lsNode.style.display='none';}catch(_){}}}}).observe(lsNode,{attributes:true,attributeFilter:['class','style']});}}catch(_){}
try{window.addEventListener('message',function(messageEvent){var kind='';try{kind=messageEvent.data&&messageEvent.data.type;}catch(_){}
if(kind){try{console.error('[LBS-F] message type='+kind);}catch(_){}}});}catch(_){}
try{document.addEventListener('visibilitychange',function(){try{console.error('[LBS-F] visibility hidden='+document.hidden);}catch(_){}});window.addEventListener('beforeunload',function(){var status='';try{status=document.getElementById('ls-text').textContent;}catch(_){}
try{console.error('[LBS-F] beforeunload status=['+status+']');}catch(_){}});}catch(_){}})();