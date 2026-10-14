// Полная копия логики раннера, но с диагностикой на каждом шаге
const fs = require('fs'), path = require('path');
let CDP; try { CDP = require('chrome-remote-interface'); } catch(e){ console.error('no CRI'); process.exit(1); }
process.on('unhandledRejection', e => console.log('UNHANDLED REJECTION:', String(e && e.stack || e).slice(0,500)));
process.on('uncaughtException', e => console.log('UNCAUGHT:', String(e && e.stack || e).slice(0,600)));

const src = fs.readFileSync('scripts/royal_capture_all_in_one.js','utf8');
const m = src.match(/const HIJACK_SRC = String\.raw`([\s\S]*?)\n`;/);
console.log('HIJACK_SRC extracted:', !!m, m && m[1].length);
const HIJACK_SRC = m[1];

const PORT = 9222;
const attached = new Set(); const clients = []; const dumpers = [];
const log = (...a)=>console.log('[attach]',...a);

async function attachToTarget(targetInfo) {
  const targetId = targetInfo && targetInfo.targetId;
  if (!targetId || attached.has(targetId)) return;
  attached.add(targetId);
  let client;
  try { client = await CDP({ port: PORT, target: targetId }); }
  catch (e) { log('connect fail', String(e.message).slice(0,120)); attached.delete(targetId); return; }
  console.log('  step: connected', targetId.slice(0,8));
  const { Network, Page, Runtime, Log } = client;
  console.log('  step: destructured');
  try { await Page.enable(); await Page.addScriptToEvaluateOnNewDocument({ source: HIJACK_SRC }); console.log('  step: initscript ok'); } catch (e){ console.log('  step: initscript err', String(e.message).slice(0,100)); }
  const reqMap = new Map();
  await Network.enable().catch((e) => { log('Network.enable не удался:', e.message); });
  console.log('  step: network enabled');
  Network.requestWillBeSent(()=>{}); Network.responseReceived(()=>{}); Network.loadingFinished(async()=>{});
  try { await Log.enable(); Log.on('entryAdded', ()=>{}); console.log('  step: log enabled'); } catch (_) {}
  await Runtime.enable().catch((e) => { log('Runtime.enable не удался:', e.message); });
  console.log('  step: runtime enabled');
  Runtime.on('consoleAPICalled', ()=>{});
  await Runtime.addBinding({ name: '__hijack_send' }).catch(()=>{});
  Runtime.on('bindingCalled', ()=>{});
  console.log('  step: binding done');
  clients.push(client);
  client.on('destroyed', () => attached.delete(targetId));
  client.on('error', () => attached.delete(targetId));
  log('+ таргет:', targetId.slice(0,8), '-', (targetInfo.url||'').slice(0,60));
  try { await Runtime.evaluate({ expression: HIJACK_SRC, includeCommandLineAPI: false }); console.log('  step: live eval ok'); } catch(e){ console.log('  step: live eval err', String(e.message).slice(0,100)); }
  dumpers.push(async () => {});
}

(async () => {
  const tabs = await CDP.List({ port: PORT });
  console.log('tabs:', tabs.filter(t=>t.type==='page').length);
  for (const t of tabs) if (t.type === 'page') await attachToTarget(t);
  console.log('after loop, attached.size =', attached.size);
  const browser = await CDP({ port: PORT });
  await browser.Target.setDiscoverTargets({ discover: true });
  browser.Target.on('targetCreated', async ({ targetInfo }) => { if (targetInfo.type==='page') await attachToTarget(targetInfo); });
  console.log('SESSION READY, targets:', attached.size);
  setTimeout(async () => { for (const c of clients) { try { await c.close(); } catch(_){} } try{await browser.close();}catch(_){} process.exit(0); }, 3000);
})().catch(e => { console.error('Ошибка:', e && e.stack || e); process.exit(1); });
