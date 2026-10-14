// hijack_attach.js — запуск crypto_hijack.js через CDP ДО навигации.
// Требует: Google Chrome с --remote-debugging-port=9222 (как при сборке captures/)
//   npm i chrome-remote-interface   (или используйте ваш существующий cdp_run.js)
// Использование:
//   node hijack_attach.js https://kys.linkvertise.lol/<нужный URL задачи>
// Что делает:
//   1. подключается к /json/new (новая вкладка)
//   2. Page.addScriptToEvaluateOnNewDocument(crypto_hijack.js)  <- критично: init script
//   3. слушает Runtime.consoleAPICalled -> пишет [HIJACK]-записи в hijack_log.jsonl
//   4. после навигации + N секунд вытаскивает window.__HIJACK_DUMP__() и wasm-дампы
//      через Runtime.evaluate с returnByValue (wasm — чанками base64).
const CDP = require('chrome-remote-interface');
const fs = require('fs');
const path = require('path');

const TARGET_URL = process.argv[2] || 'about:blank';
const SESSION_SEC = parseInt(process.argv[3] || '90', 10);
const SCRIPT = fs.readFileSync(path.join(__dirname, 'crypto_hijack.js'), 'utf8');
const OUT = path.join(__dirname, '..', 'captures_hijack_' + Date.now());

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const tab = await CDP.New({ port: 9222 });
  const client = await CDP({ port: 9222, target: tab.id });
  const { Page, Runtime } = client;

  const jf = fs.createWriteStream(path.join(OUT, 'hijack_log.jsonl'));
  Runtime.enable();
  Runtime.on('consoleAPICalled', (e) => {
    if (!e.args || !e.args.length) return;
    const first = e.args[0];
    if (first.type === 'string' && first.value === '[HIJACK]' && e.args[1]) {
      jf.write((e.args[1].value || JSON.stringify(e.args[1].unserializableValue)) + '\n');
    } else {
      jf.write(JSON.stringify({ _rawConsole: e.type, args: e.args.map(a => a.value ?? a.description ?? String(a.unserializableValue)) }) + '\n');
    }
  });

  // ГЛАВНОЕ: init-скрипт выполняется в новом document до любого кода страницы
  await Page.enable();
  await Page.addScriptToEvaluateOnNewDocument({ source: SCRIPT });
  await Page.navigate({ url: TARGET_URL });

  console.log('[*] hijack attached, session', SESSION_SEC, 's ->', OUT);
  await new Promise(r => setTimeout(r, SESSION_SEC * 1000));

  // выгрузка
  const dump = await Runtime.evaluate({ expression: 'window.__HIJACK_DUMP__ ? window.__HIJACK_DUMP__() : null', returnByValue: true });
  if (dump.result && dump.result.value) {
    fs.writeFileSync(path.join(OUT, 'hijack_structured.json'), dump.result.value);
    console.log('[+] structured log saved,', dump.result.value.length, 'bytes');
  }
  const wasms = await Runtime.evaluate({ expression: 'JSON.stringify(window.__HIJACK_WASMS__ ? window.__HIJACK_WASMS__() : [])', returnByValue: true });
  console.log('[*] wasm dumps present:', wasms.result && wasms.result.value);
  // скачиваем каждый wasm base64-чанками (на случай больших модулей)
  const list = JSON.parse((wasms.result && wasms.result.value) || '[]');
  for (let i = 0; i < list.length; i++) {
    const b64 = await Runtime.evaluate({
      expression: `(function(){const w=(window.__WASM_DUMPS__||[])[${i}];if(!w)return null;let s='',u=w.bytes;for(let o=0;o<u.length;o+=0x8000)s+=String.fromCharCode.apply(null,u.subarray(o,o+0x8000));return btoa(s);})()`,
      returnByValue: true,
    });
    if (b64.result && b64.result.value) {
      fs.writeFileSync(path.join(OUT, 'vm_' + i + '_' + (list[i].where || '').replace(/[^a-z0-9]+/gi, '_') + '.wasm'), Buffer.from(b64.result.value, 'base64'));
      console.log('[+] wrote vm_' + i + '.wasm (' + list[i].size + ' bytes)');
    }
  }
  jf.end();
  await client.close();
  console.log('[done]', OUT);
})().catch(e => { console.error(e); process.exit(1); });
