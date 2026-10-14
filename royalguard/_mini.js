// Мини-версия логики attach из royal_capture_all_in_one.js с диагностикой
const fs = require('fs'), path = require('path');
const CDP = require('chrome-remote-interface');
const PORT = 9222;
(async () => {
  const tabs = await CDP.List({ port: PORT });
  console.log('tabs total:', tabs.length, 'pages:', tabs.filter(t=>t.type==='page').length);
  for (const t of tabs) if (t.type === 'page') {
    console.log('attaching', t.id, t.url.slice(0,40));
    let client;
    try { client = await CDP({ port: PORT, target: t.id }); }
    catch (e) { console.log('  CONNECT FAIL', String(e.message).slice(0,150)); continue; }
    const { Network, Page, Runtime, Log } = client;
    console.log('  domains:', typeof Network.enable, typeof Page.addScriptToEvaluateOnNewDocument, typeof Runtime.addBinding, typeof Log.enable);
    try { await Page.enable(); await Page.addScriptToEvaluateOnNewDocument({ source: '// test' }); console.log('  init-script OK'); } catch(e){ console.log('  init-script FAIL', String(e.message).slice(0,120)); }
    try { await Network.enable(); console.log('  Network OK'); } catch(e){ console.log('  Network FAIL', String(e.message).slice(0,120)); }
    try { await Log.enable(); console.log('  Log OK'); } catch(e){ console.log('  Log FAIL', String(e.message).slice(0,120)); }
    try { await Runtime.enable(); console.log('  Runtime OK'); } catch(e){ console.log('  Runtime FAIL', String(e.message).slice(0,120)); }
    try { await Runtime.addBinding({ name: '__hijack_send' }); console.log('  binding OK'); } catch(e){ console.log('  binding FAIL', String(e.message).slice(0,120)); }
    // без await — как в раннере? нет, в раннере есть await. Проверим evaluate HIJACK_SRC
    console.log('  attached fully to', t.id);
    // не закрываем, имитируем жизнь
  }
  setTimeout(()=>process.exit(0), 500);
})().catch(e=>{console.error('OUTER ERR', e && e.stack || e); process.exit(1)});
