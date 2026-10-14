#!/usr/bin/env node
// ============================================================================
// capture_attach.js — захват сессии из УЖЕ ЗАПУЩЕННОГО браузера
//
// Сценарий: ты сам запускаешь Chrome, сам кликаешь по промежуточным страницам
// (Madium -> kys.linkvertise.lol -> iframe lootlabs и т.д.), скрипт пишет ВСЁ:
//   - трафик (fetch/XHR/beacon)          в out/traffic.jsonl
//   - консоль / события                  в out/events.log
//   - перехваченные crypto_hijack ключи/plaintext RTDL в out/crypto.jsonl
//   - исходники скриптов страницы        в out/scripts/NNNN_<name>.js
//   - тела ответов                       в out/responses/
//   - дамп window.__HIJACK_DUMP__ в конце в out/hijack_structured.json
//
// ── Шаг 1. Запусти браузер с debug-портом И выключенными фоновыми вкладками ──
//   google-chrome-stable --remote-debugging-port=9222 \
//       --disable-backgrounding-occluded-windows \
//       --disable-renderer-backgrounding \
//       --disable-background-timer-throttling
//
//   ВАЖНО про «промежуточки»:Royal Guard следит за visibility вкладки (RTDL).
//   Без флагов --disable-* выше, если ты свернёшь окно или переключишься на
//   другой табы, сайт уйдёт в "hidden" и RTDL начнёт слать события скрытия
//   (или оборвёт handshake). Флаги отключают троттлинг/фоновый режим.
//
//   Если нужно несколько окон/профилей — добавь свой --user-data-dir=/tmp/p1,
//   иначе новый запущенный Chrome подключится к уже открытому окну без порта.
//
// ── Шаг 2. Запусти этот скрипт (URL НЕ нужен) ──
//   npm i chrome-remote-interface     # один раз
//   node capture_attach.js            # порт 9222 по умолчанию
//   node capture_attach.js 9333       # свой порт
//   RECORD_SEC=600 node capture_attach.js   # автостоп через 10 мин (по умолчанию — до Ctrl-C)
//
// ── Шаг 3. Кликай по сайту. Стоп — Ctrl-C (аккуратно завершит запись) ──
//
// Скрипт автоматически отслеживает НОВЫЕ вкладки/таргеты и навешивает
// crypto_hijack.js как init-script ДО загрузки любой страницы — то есть
// перехватывается даже тот код, что выполняется на самых ранних этапах.
// ============================================================================

const fs = require('fs');
const path = require('path');

let CDP;
try { CDP = require('chrome-remote-interface'); }
catch (e) {
  console.error('Не хватает зависимости. Выполните:  npm i chrome-remote-interface');
  process.exit(1);
}

const PORT = parseInt(process.argv[2] || '9222', 10);
const AUTO_STOP_SEC = parseInt(process.env.RECORD_SEC || '0', 10); // 0 = до Ctrl-C
const HIJACK_SRC = fs.readFileSync(path.join(__dirname, 'crypto_hijack.js'), 'utf8');

const OUT_DIR = path.join(__dirname, '..', 'captures',
  'attach_' + new Date().toISOString().replace(/[:.]/g, '-'));
const SCRIPTS_DIR = path.join(OUT_DIR, 'scripts');
const RESP_DIR = path.join(OUT_DIR, 'responses');
for (const d of [OUT_DIR, SCRIPTS_DIR, RESP_DIR]) fs.mkdirSync(d, { recursive: true });

const trafficPath = path.join(OUT_DIR, 'traffic.jsonl');
const eventsPath  = path.join(OUT_DIR, 'events.log');
const cryptoPath  = path.join(OUT_DIR, 'crypto.jsonl');
const log = (...a) => console.log('[attach]', ...a);
const stamp = () => new Date().toISOString();

const tStream = fs.createWriteStream(trafficPath, { flags: 'a' });
const eStream = fs.createWriteStream(eventsPath,  { flags: 'a' });
const cStream = fs.createWriteStream(cryptoPath,  { flags: 'a' });
const write = (s, o) => s.write(JSON.stringify(o) + '\n');
const event = (msg, extra) => eStream.write(`${stamp()} ${msg}${extra ? ' ' + JSON.stringify(extra) : ''}\n`);

let reqCounter = 0;
const attached = new Set();      // targetId, к которым уже подключились

async function attachToTarget(targetInfo) {
  const targetId = targetInfo && targetInfo.targetId;
  if (!targetId || attached.has(targetId)) return;
  attached.add(targetId);
  let client;
  try { client = await CDP({ port: PORT, target: targetId }); }
  catch (e) { log('не удалось подключиться к таргету', targetId, '-', String(e.message).slice(0, 120)); return; }

  const { Network, Page, Runtime, Log } = client;

  // КРИТИЧНО: init-script внедряется ДО выполнения любого кода страницы
  try {
    await Page.enable();
    await Page.addScriptToEvaluateOnNewDocument({ source: HIJACK_SRC });
  } catch (_) {}

  const reqMap = new Map(); // requestId -> {id,url,type}
  await Network.enable();
  Network.requestWillBeSent(({ requestId, request, method, url, type, postData, initiator }) => {
    const id = ++reqCounter;
    reqMap.set(requestId, { id, url, type });
    write(tStream, { dir: 'req', id, ts: stamp(), method, url, type,
      headers: request.headers, postData: (postData || '').slice(0, 4000),
      initiator: initiator && initiator.type, target: targetId });
    if (/pushToTalk|PGPSC|PGPG|RTDL|handshake/i.test(url)) event('RG-ENDPOINT', { id, url });
  });
  Network.responseReceived(({ requestId, response }) => {
    const meta = reqMap.get(requestId);
    write(tStream, { dir: 'resp', id: meta && meta.id, ts: stamp(), status: response.status,
      url: response.url, type: response.type, headers: response.headers, target: targetId });
  });
  Network.loadingFinished(async ({ requestId }) => {
    const meta = reqMap.get(requestId);
    if (!meta) return;
    try {
      const { body, base64Encoded } = await Network.getResponseBody({ requestId });
      const buf = base64Encoded ? Buffer.from(body, 'base64') : Buffer.from(body, 'utf8');
      if (buf.length > 1_500_000) return;
      const name = `${String(meta.id).padStart(4, '0')}_${String(meta.url).replace(/[^a-zA-Z0-9.-]+/g, '_').slice(-90)}.js`;
      fs.writeFileSync(path.join(SCRIPTS_DIR, name), buf);
    } catch (_) {}
  });

  try {
    await Log.enable();
    Log.on('entryAdded', ({ entry }) => event(`console:${entry.level}`, { text: entry.text, source: entry.url }));
  } catch (_) {}

  await Runtime.enable();
  Runtime.on('consoleAPICalled', ({ type, args }) => {
    const text = (args || []).map(a => a.value !== undefined ? String(a.value) : (a.description || a.type)).join(' ');
    event(`runtime:${type}`, { text });
    if (text.startsWith('[HIJACK]')) cStream.write(text.slice('[HIJACK]'.length).trim() + '\n');
  });
  await Runtime.addBinding({ name: '__hijack_send' }).catch(() => {});
  Runtime.on('bindingCalled', ({ name, payload }) => {
    if (name === '__hijack_send') cStream.write(payload + '\n');
  });

  client.on('destroyed', () => { attached.delete(targetId); });
  client.on('error',     () => { attached.delete(targetId); });
  clients.push(client);
  log('+ таргет:', targetId, '-', (targetInfo.url || '').slice(0, 100));

  // периодически вытаскиваем полный hijack-дамп (страховка от обрезки консоли)
  dumpers.push(async () => {
    try {
      const { result } = await Runtime.evaluate({
        expression: 'window.__HIJACK_DUMP__ ? window.__HIJACK_DUMP__() : ""', returnByValue: true });
      if (result && result.value) {
        try { JSON.parse(result.value).forEach(o => cStream.write(JSON.stringify(o) + '\n')); }
        catch (_) { cStream.write(result.value + '\n'); }
      }
    } catch (_) {}
  });
}

const clients = [];
const dumpers = [];

(async () => {
  // проверка, что браузер вообще слушает debug-порт
  let tabs;
  try { tabs = await CDP.List({ port: PORT }); }
  catch (e) {
    console.error(
      `Не могу подключиться к Chrome на порту ${PORT}.\n` +
      `Запусти браузер с флагами, например:\n\n` +
      `  google-chrome-stable --remote-debugging-port=${PORT} \\\n` +
      `      --disable-backgrounding-occluded-windows --disable-renderer-backgrounding \\\n` +
      `      --disable-background-timer-throttling\n\n` +
      `и уже в нём открывай нужный сайт.`);
    process.exit(1);
  }

  // подключаемся ко всем уже открытым page-таргетам
  for (const t of tabs) if (t.type === 'page') await attachToTarget(t);

  // и к новым вкладкам, которые ты будешь открывать по ходу «промежуточков»
  const browser = await CDP({ port: PORT });
  await browser.Target.setDiscoverTargets({ discover: true });
  browser.Target.on('targetCreated', async ({ targetInfo }) => {
    if (targetInfo.type === 'page') await attachToTarget(targetInfo);
  });

  event('SESSION-START', { mode: 'attach', port: PORT, targets: attached.size });
  log(`Пишу всё в: ${OUT_DIR}`);
  log(`Подключено вкладок: ${attached.size}. Кликай по сайту. Останов — Ctrl-C.` +
      (AUTO_STOP_SEC ? ` (автостоп через ${AUTO_STOP_SEC}с)` : ''));

  const iv = setInterval(() => dumpers.forEach(f => f().catch(() => {})), 10000);

  let stopping = false;
  async function stop(sig) {
    if (stopping) return; stopping = true;
    clearInterval(iv);
    event('SESSION-END', { requests: reqCounter, sig: sig || 'auto' });
    // финальный сбор hijack-дампа со всех вкладок
    for (const f of dumpers) { try { await f(); } catch (_) {} }
    // и сохранение структурированного дампа первой активной вкладки
    for (const c of clients) {
      try {
        const { result } = await c.Runtime.evaluate({
          expression: 'window.__HIJACK_DUMP__ ? window.__HIJACK_DUMP__() : null', returnByValue: true });
        if (result && result.value) {
          fs.writeFileSync(path.join(OUT_DIR, 'hijack_structured.json'), result.value);
          break;
        }
      } catch (_) {}
    }
    for (const c of clients) { try { await c.close(); } catch (_) {} }
    try { await browser.close(); } catch (_) {}
    log(`Готово. Запросов: ${reqCounter}. Дамп в: ${OUT_DIR}`);
    process.exit(0);
  }
  process.on('SIGINT',  () => stop('ctrl-c'));
  process.on('SIGTERM', () => stop('sigterm'));
  if (AUTO_STOP_SEC) setTimeout(() => stop('timeout'), AUTO_STOP_SEC * 1000);
})().catch(e => { console.error('Ошибка:', e && e.stack || e); process.exit(1); });
