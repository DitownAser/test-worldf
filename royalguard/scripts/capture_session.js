#!/usr/bin/env node
// ============================================================================
// capture_session.js — автономный CDP-дамп сессии Royal Guard / SquareVM
//
// Сценарий «запустил браузер через команду и всё»: скрипт САМ стартует Chrome
// с удалённым портом, сам подключается по CDP, сам внедряет crypto_hijack.js
// ДО загрузки страницы (Page.addScriptToEvaluateOnNewDocument) и пишет:
//   - трафик (fetch/XHR/beacon) в out/traffic.jsonl
//   - консольные логи    в out/events.log
//   - перехваченные ключи/plaintext RTDL в out/crypto.jsonl
//   - исходники скриптов страницы       в out/scripts/NNNN_<name>.js
//   - тела ответов                       в out/responses/
//
// Использование:
//   npm i chrome-remote-interface          # один раз
//   node capture_session.js <URL> [сек]    # сек — длительность записи (90)
//   node capture_session.js https://kys.linkvertise.lol/<TID> 120
//
// Требования: установленный Google Chrome / Chromium (Linux/macOS). Путь можно
//   задать через переменную окружения CHROME_BIN. Если Chrome не найден по
//   типичным путям, скрипт сам ищет бинарник в PATH (google-chrome-stable,
//   google-chrome, chromium-browser, chromium, brave-browser, microsoft-edge
//   и т.д.). Профиль — временный (не трогаем основной).
// ============================================================================

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn, execSync } = require('child_process');

let CDP;
try { CDP = require('chrome-remote-interface'); }
catch (e) {
  console.error('Не хватает зависимости. Выполните:  npm i chrome-remote-interface');
  process.exit(1);
}

const URL_TARGET = process.argv[2];
if (!URL_TARGET) {
  console.error('Использование: node capture_session.js <URL> [seconds]');
  process.exit(1);
}
const DURATION = parseInt(process.argv[3] || '90', 10);

const OUT_DIR = path.join(__dirname, '..', 'captures',
  'live_' + new Date().toISOString().replace(/[:.]/g, '-'));
const SCRIPTS_DIR = path.join(OUT_DIR, 'scripts');
const RESP_DIR = path.join(OUT_DIR, 'responses');
for (const d of [OUT_DIR, SCRIPTS_DIR, RESP_DIR]) fs.mkdirSync(d, { recursive: true });

const trafficPath = path.join(OUT_DIR, 'traffic.jsonl');
const eventsPath = path.join(OUT_DIR, 'events.log');
const cryptoPath = path.join(OUT_DIR, 'crypto.jsonl'); // то, что присылает crypto_hijack.js
const log = (...a) => console.log('[capture]', ...a);

function findChrome() {
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;

  // 1. Типичные пути Linux / macOS
  const candidates = [
    '/usr/bin/google-chrome-stable',   // официальный deb-пакет Google
    '/usr/bin/google-chrome',
    '/opt/google/chrome/chrome',       // прямой путь внутри deb-пакета
    '/usr/bin/google-chrome-beta',
    '/usr/bin/google-chrome-unstable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/chrome',
    '/snap/bin/chromium',              // snap
    '/var/lib/flatpak/exports/bin/org.chromium.Chromium',
    '/usr/bin/brave-browser',
    '/usr/bin/brave-browser-stable',
    '/usr/bin/microsoft-edge',
    '/usr/bin/microsoft-edge-stable',
    '/usr/lib/chromium/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    path.join(os.homedir(), '.config/brave/software/brave-browser'),
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;

  // 2. Ищем исполняемое имя в PATH (покрывает нестандартные установки)
  const names = ['google-chrome-stable', 'google-chrome', 'chromium-browser',
                 'chromium', 'chrome', 'brave-browser', 'microsoft-edge'];
  let whichOut = '';
  try { whichOut = execSync('which -a ' + names.join(' ') + ' 2>/dev/null || true').toString(); } catch (_) {}
  for (const line of whichOut.split('\n')) {
    const p = line.trim();
    if (p && fs.existsSync(p)) return p;
  }

  // 3. Быстрый обход /usr/bin, /usr/local/bin, /opt на *.app/chrome-подобные бинарники
  const dirs = ['/usr/bin', '/usr/local/bin', '/opt/google/chrome', '/usr/lib/chromium'];
  for (const d of dirs) {
    let entries = [];
    try { entries = fs.readdirSync(d); } catch (_) { continue; }
    const hit = entries.find(e => /^(google-chrome|chromium|chrome|brave|microsoft-edge)/i.test(e));
    if (hit) {
      const full = path.join(d, hit);
      try { fs.accessSync(full, fs.constants.X_OK); return full; } catch (_) {}
    }
  }

  throw new Error(
    'Chrome не найден. Задайте путь явно:  CHROME_BIN=/путь/к/chrome node capture_session.js <URL>\n' +
    'Поддерживаются: google-chrome-stable, google-chrome, chromium, chromium-browser, brave, edge.'
  );
}

(async () => {
  // ---- 1. Сам запускаем Chrome с debug-портом и init-перехватом -------------
  const port = 9333;
  const profileDir = path.join(OUT_DIR, 'profile');
  const chromeBin = findChrome();
  log('Запуск браузера:', chromeBin);
  const browserProc = spawn(chromeBin, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run', '--no-default-browser-check',
    '--disable-blink-features=AutomationControlled',
    // headless=false: нам нужен реальный фокус/видимость вкладки — RTDL
    // отслеживает visibilitychange и шлёт события скрытия окна
    '--new-window', 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  // stderr Chrome (например "DevTools listening on ..." или ошибки sandbox на Linux)
  browserProc.stderr.on('data', d => {
    const s = String(d).trim();
    if (s) log('chrome:', s.slice(0, 200));
  });
  browserProc.on('exit', (code) => {
    console.error(`[capture] Браузер завершился сам (код ${code}). Если это Linux и ошибка sandbox — перезапустите с флагом суффиксом --no-sandbox или проверьте, что профиль-дир доступен на запись.`);
  });
  process.on('exit', () => { try { browserProc.kill('SIGKILL'); } catch (_) {} });
  process.on('SIGINT', () => { try { browserProc.kill('SIGKILL'); } catch (_) {} process.exit(130); });

  // ждём подъёма DevTools-эндпоинта
  const waitUp = async (tries = 40) => {
    for (let i = 0; i < tries; i++) {
      try { await CDP.List({ port }); return; } catch (_) {
        await new Promise(r => setTimeout(r, 500));
      }
    }
    throw new Error('Chrome не поднял remote-debugging порт');
  };
  await waitUp();
  log('Браузер готов на порту', port);

  // ---- 2. Подключаемся к первой вкладке --------------------------------------
  const tabs = await CDP.List({ port });
  const page = tabs.find(t => t.type === 'page') || tabs[0];
  const client = await CDP({ port, target: page });
  const { Network, Page, Runtime, Log } = client;

  // ---- 3. Внедряем crypto_hijack.js ДО любой навигации ----------------------
  const hijackSrc = fs.readFileSync(path.join(__dirname, 'crypto_hijack.js'), 'utf8');
  await Page.enable();
  await Page.addScriptToEvaluateOnNewDocument({ source: hijackSrc });
  log('crypto_hijack.js зарегистрирован как init-script (до загрузки страницы)');

  // ---- 4. Журналирование ------------------------------------------------------
  const tStream = fs.createWriteStream(trafficPath, { flags: 'a' });
  const eStream = fs.createWriteStream(eventsPath, { flags: 'a' });
  const cStream = fs.createWriteStream(cryptoPath, { flags: 'a' });
  const stamp = () => new Date().toISOString();
  const write = (s, o) => s.write(JSON.stringify(o) + '\n');
  const event = (msg, extra) => {
    eStream.write(`${stamp()} ${msg}${extra ? ' ' + JSON.stringify(extra) : ''}\n`);
  };

  let reqCounter = 0;
  const reqMap = new Map();      // requestId -> id (для сохранения исходников)

  await Network.enable();
  Network.requestWillBeSent(({ requestId, request, method, type, postData, initiator }) => {
    const id = ++reqCounter;
    // БАГ ИСПРАВЛЕН: url берём из request.url — корневого поля url в событии нет
    const url = (request && request.url) || '';
    reqMap.set(requestId, id);
    write(tStream, { dir: 'req', id, ts: stamp(), method, url, type,
      headers: request.headers, postData: (postData || '').slice(0, 4000),
      initiator: initiator && initiator.type });
    if (/pushToTalk|PGPSC|PGPG|RTDL|handshake/i.test(url)) event('RG-ENDPOINT', { id, url });
  });
  Network.responseReceived(({ requestId, response }) => {
    write(tStream, { dir: 'resp', id: reqMap.get(requestId), ts: stamp(), status: response.status,
      url: response.url, type: response.type, headers: response.headers });
  });
  Network.loadingFinished(({ requestId }) => {
    // сохраняем исходники страниц на диск (как в исходном дампе captures/)
    Network.getResponseBody({ requestId }).then(({ body, base64Encoded }) => {
      const meta = reqMap.get(requestId);
      if (!meta) return;
      const buf = base64Encoded ? Buffer.from(body, 'base64') : Buffer.from(body, 'utf8');
      if (buf.length > 1_500_000) return; // пропускаем гигантские бандлы
      const name = `${String(meta.id).padStart(4, '0')}_${url.replace(/[^a-zA-Z0-9.-]+/g, '_').slice(-90)}.js`;
      fs.writeFileSync(path.join(SCRIPTS_DIR, name), buf);
    }).catch(() => {});
  });

  await Log.enable();
  Log.entryAdded(({ entry }) => {
    event(`console:${entry.level}`, { text: entry.text, source: entry.url });
  });
  Runtime.consoleAPICalled(({ type, args }) => {
    const text = args.map(a => a.value !== undefined ? String(a.value) : (a.description || a.type)).join(' ');
    event(`runtime:${type}`, { text });
    // crypto_hijack.sh отправляет перехваченное через console с префиксом [HIJACK]
    if (text.startsWith('[HIJACK]')) {
      cStream.write(text.slice('[HIJACK]'.length).trim() + '\n');
    }
  });
  // плюс канал через binding, если hijack его использует
  await Runtime.addBinding({ name: '__hijack_send' }).catch(() => {});
  Runtime.bindingCalled(({ name, payload }) => {
    if (name === '__hijack_send') cStream.write(payload + '\n');
  });

  // ---- 4b. Периодический сбор дампа из окна страницы ------------------------
  // crypto_hijack.js хранит всё в window.__HIJACK_DUMP__ и дублирует в консоль;
  // дополнительно вытаскиваем полный дамп каждые 10 секунд (страховка от
  // обрезки console-сообщений) и скачиваем wasm-модули ВМ на диск.
  setInterval(async () => {
    try {
      const { result } = await Runtime.evaluate({ expression: 'window.__HIJACK_DUMP__ ? window.__HIJACK_DUMP__() : ""', returnByValue: true });
      if (result && result.value) {
        try { JSON.parse(result.value).forEach(o => cStream.write(JSON.stringify(o) + '\n')); }
        catch (_) { cStream.write(result.value + '\n'); }
      }
    } catch (_) {}
  }, 10000);

  // ---- 5. Навигация и запись --------------------------------------------------
  event('SESSION-START', { url: URL_TARGET, durationSec: DURATION });
  log('Открываем:', URL_TARGET);
  await Page.navigate({ url: URL_TARGET });

  await new Promise(r => setTimeout(r, DURATION * 1000));

  event('SESSION-END', { requests: reqCounter });
  log(`Готово. Запросов: ${reqCounter}. Дамп в: ${OUT_DIR}`);
  await client.close().catch(() => {});
  try { browserProc.kill('SIGKILL'); } catch (_) {}
  process.exit(0);
})().catch(e => { console.error('Ошибка:', e.message); process.exit(1); });
