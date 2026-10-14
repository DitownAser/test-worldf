const fs = require('fs'), path = require('path');
const CDP = require('chrome-remote-interface');
process.on('unhandledRejection', e => console.log('UNHANDLED REJECTION:', String(e && e.message || e).slice(0,200)));
process.on('uncaughtException', e => console.log('UNCAUGHT:', String(e && e.stack || e).slice(0,400)));
(async () => {
  const tabs = await CDP.List({ port: 9222 });
  for (const t of tabs) if (t.type === 'page') {
    console.log('attaching', t.id.slice(0,8));
    let client;
    try { client = await CDP({ port: 9222, target: t.id }); }
    catch (e) { console.log('CONNECT FAIL', String(e.message).slice(0,150)); continue; }
    const { Network, Page, Runtime, Log } = client;
    try {
      await Page.enable();
      await Page.addScriptToEvaluateOnNewDocument({ source: '// test' });
    } catch (_) {}
    await Network.enable().catch((e) => { console.log('Network.enable не удался:', e.message); });
    Network.requestWillBeSent(() => {});
    Network.responseReceived(() => {});
    Network.loadingFinished(async () => {});
    try { await Log.enable(); Log.on('entryAdded', () => {}); } catch (_) {}
    await Runtime.enable().catch((e) => { console.log('Runtime.enable не удался:', e.message); });
    Runtime.on('consoleAPICalled', () => {});
    await Runtime.addBinding({ name: '__hijack_send' }).catch(() => {});
    Runtime.on('bindingCalled', () => {});
    clients.push(client);
    client.on('destroyed', () => {});
    client.on('error', () => {});
    console.log('+ таргет:', t.id.slice(0,8), '-', (t.url||'').slice(0,50));
    try { await Runtime.evaluate({ expression: 'void 0', includeCommandLineAPI: false }); console.log('evaluate OK'); } catch (_) { console.log('evaluate threw'); }
    dumpers.push(async () => {});
  }
  console.log('attached count:', attached.size = clients.length);
  const browser = await CDP({ port: 9222 });
  await browser.Target.setDiscoverTargets({ discover: true });
  browser.Target.on('targetCreated', () => {});
  console.log('browser ws OK, targets discovered');
  process.exit(0);
})().catch(e => { console.error('OUTER:', e && e.stack || e); process.exit(1); });
const clients = [], dumpers = [];
