#!/usr/bin/env node
// ============================================================================
//  ROYALGUARD — ALL-IN-ONE ЗАХВАТ СЕССИИ ИЗ УЖЕ ЗАПУЩЕННОГО БРАУЗЕРА
//  Один файл, две секции:
//
//    [СЕКЦИЯ A] crypto_hijack (встраивается в страницы как init-script)
//      - SubtleCrypto: generateKey/importKey/deriveBits/deriveKey/encrypt/
//        decrypt/sign/digest  -> ключи, IV, ГОТОВЫЙ plaintext RTDL
//      - WebAssembly.instantiate* -> слив модуля SquareVM (.wasm) + таблицы
//        импортов/экспортов (граница "ВМ <-> JS")
//      - fetch/XHR/sendBeacon  -> привязка шифротекста к моменту encrypt()
//      - геттеры window.crypto/Crypto/SubtleCrypto -> МОМЕНТ доступа ВМ
//      - анти-анти-отладка: disguise() возвращает native-вид обёрток
//
//    [СЕКЦИЯ B] CDP-раннер (Node)
//      - подключается к Chrome на --remote-debugging-port (по умолч. 9222)
//      - цепляется ко ВСЕМ уже открытым page-таргетам
//      - Target.setDiscoverTargets/targetCreated -> ловит НОВЫЕ вкладки
//        («промежуточки» Madium -> kys.linkvertise.lol -> iframe lootlabs),
//        на каждый новый таргет crypto_hijack навешивается init-scriptом
//        ДО загрузки страницы (Page.addScriptToEvaluateOnNewDocument)
//      - пишет всё в royalguard/captures/attach_<дата>/ :
//          traffic.jsonl   все запросы/ответы со всех вкладок (+headers/body)
//          events.log      консоль/события/RG-ENDPOINT/WASM-SAVED
//          crypto.jsonl    перехваты crypto_hijack (ключи/plaintext RTDL)
//          scripts/        исходники страниц и inline-скриптов
//          wasm/           дампнутые .wasm-модули SquareVM
//          responses/      тела ответов по RG-эндпоинтам
//          hijack_structured.json  полный структурированный дамп в конце
//
//  ── Шаг 1. Запусти браузер с debug-портом И выключенным фоновым троттлингом
//      google-chrome-stable --remote-debugging-port=9222 \
//          --disable-backgrounding-occluded-windows \
//          --disable-renderer-backgrounding \
//          --disable-background-timer-throttling
//    ВАЖНО: Royal Guard следит за visibility вкладки (RTDL). Без флагов выше,
//    если свернёшь окно — сайт уйдёт в "hidden" и handshake оборвётся.
//    Для второго профиля добавь --user-data-dir=/tmp/p1.
//
//  ── Шаг 2. npm i chrome-remote-interface && node royal_capture_all_in_one.js
//      node royal_capture_all_in_one.js            # порт 9222
//      node royal_capture_all_in_one.js 9333       # свой порт
//      RECORD_SEC=600 node royal_capture_all_in_one.js   # автостоп через 10 мин
//
//  ── Шаг 3. Кликай по сайту до конца «промежуточков». Стоп — Ctrl-C.
//
//  Автоматическое «выполни заказ за меня» невозможнo: Linkvertise/LootLabs
//  требуют человеческие проверки (реклама/капча/visibility). Этот инструмент
//  захватывает всё, что происходит в твоей живой сессии.
// ============================================================================

'use strict';

const fs = require('fs');
const path = require('path');

// ############################################################################
// ###                                                                      ###
// ###  СЕКЦИЯ A — КОД, КОТОРЫЙ ВНЕДРЯЕТСЯ В СТРАНИЦУ (crypto_hijack)       ###
// ###  Обёрнут в строку-шаблон raw, чтобы не конфликтовать с Node-скоупом. ###
// ###                                                                      ###
// ############################################################################

const HIJACK_SRC = String.raw`
(function () {
  'use strict';
  if (window.__HIJACK_INSTALLED__) return;
  window.__HIJACK_INSTALLED__ = true;

  // ---------- утилиты -------------------------------------------------------
  const LOG = [];
  // лимит binding-сообщений: при плотном RTDL-трафике не переполнять CDP-буфер
  let sentCount = 0;
  const SENT_LIMIT = 3000;
  const b64 = (buf) => {
    try {
      const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
      let s = '';
      for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
      return btoa(s);
    } catch (e) { return null; }
  };
  const hex = (buf) => {
    try {
      const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
      return Array.from(u8.slice(0, 32)).map(b => b.toString(16).padStart(2, '0')).join('');
    } catch (e) { return null; }
  };
  const now = () => performance.now().toFixed(1);
  const utf8 = (u8, max) => { try { return new TextDecoder().decode(u8).slice(0, max || 2000); } catch (e) { return null; } };

  // канал в CDP: binding __hijack_send (раннер объявляет Runtime.addBinding).
  // Не зависит от формата console-логов; console.log остаётся страховкой.
  const send = (obj) => {
    try {
      if (typeof window.__hijack_send === 'function' && sentCount < SENT_LIMIT) {
        window.__hijack_send(JSON.stringify(obj));
        sentCount++;
      }
    } catch (e) {}
  };
  const rec = (obj) => {
    obj.t = now();
    LOG.push(obj);
    send(obj);
    try { console.log('[HIJACK]', JSON.stringify(obj)); } catch (e) {}
  };

  // ---------- анти-анти-отладка: маскировка обёрток под нативные ------------
  const fakeNative = new WeakMap();
  function disguise(fn, nativeFn) {
    fakeNative.set(fn, Function.prototype.toString.call(nativeFn));
    return fn;
  }
  const origToString = Function.prototype.toString;
  Function.prototype.toString = function () {
    if (fakeNative.has(this)) return fakeNative.get(this);
    return origToString.call(this);
  };

  // безопасная сериализация параметров алгоритма: новые движки (PQC/ML-KEM)
  // кладут BigInt в alg — JSON.stringify на них падает, а rec() вне try
  // обрушил бы всю операцию шифрования страницы.
  const safeAlg = (alg) => {
    try {
      if (alg == null) return null;
      if (typeof alg !== 'object') return String(alg);
      const out = {};
      for (const k of Object.keys(alg)) {
        const v = alg[k];
        if (typeof v === 'bigint') out[k] = String(v);
        else if (v instanceof ArrayBuffer || ArrayBuffer.isView(v)) out[k] = hex(v);
        else if (typeof v === 'object' && v !== null) {
          try { out[k] = JSON.parse(JSON.stringify(v, (kk, vv) => typeof vv === 'bigint' ? String(vv) : vv)); }
          catch (e) { out[k] = String(v); }
        } else out[k] = v;
      }
      return out;
    } catch (e) { return { name: (() => { try { return alg.name; } catch (e2) { return '?'; } })(), unparsable: true }; }
  };

  // ---------- 1. SubtleCrypto -----------------------------------------------
  // Самый ценный перехват: на входе decrypt() серверного ответа и выходе
  // encrypt() пакетов pushToTalk получаем УЖЕ ГОТОВЫЙ plaintext RTDL —
  // без реверса байткода SquareVM.
  const subtle = crypto.subtle;
  const keyTags = new WeakMap(); // CryptoKey непрозрачен — сами вешаем метки

  const wrapMethod = (obj, name, before, after) => {
    const orig = obj[name] && obj[name].bind(obj);
    if (!orig) return;
    const wrapped = async function (...args) {
      let ctx;
      try { ctx = before && before(args); } catch (e) {}
      const res = await orig(...args);
      try { after && after(args, res, ctx); } catch (e) {}
      return res;
    };
    obj[name] = disguise(Object.defineProperty(wrapped, 'name', { value: name }), orig);
  };

  const origGenerate = subtle.generateKey.bind(subtle);
  subtle.generateKey = disguise(async function (alg, extractable, usages) {
    const key = await origGenerate(alg, extractable, usages);
    const tag = 'gen:' + (alg.name || '?') + ':' + (alg.namedCurve || alg.length || '') + '#' + LOG.length;
    keyTags.set(key, tag);
    if (key && key.privateKey) keyTags.set(key.privateKey, tag + '/priv');
    if (key && key.publicKey) keyTags.set(key.publicKey, tag + '/pub');
    rec({ op: 'generateKey', alg: safeAlg(alg), tag });
    return key;
  }, origGenerate);

  const origImport = subtle.importKey.bind(subtle);
  subtle.importKey = disguise(async function (format, keyData, alg, extractable, usages) {
    const key = await origImport(format, keyData, alg, extractable, usages);
    const tag = 'imp:' + format + ':' + (alg.name || '?');
    keyTags.set(key, tag);
    rec({
      op: 'importKey', format, alg: safeAlg(alg),
      dataHex: typeof keyData === 'string' ? keyData.slice(0, 64) : hex(keyData),
      dataFullB64: typeof keyData !== 'string' ? b64(keyData) : null,
      tag,
    });
    return key;
  }, origImport);

  const origDerive = subtle.deriveBits.bind(subtle);
  subtle.deriveBits = disguise(async function (alg, baseKey, length) {
    const bits = await origDerive(alg, baseKey, length);
    // ECDH(X25519)-секрет = общий секрет RTDL-туннеля "YX". Ловим здесь.
    rec({
      op: 'deriveBits', alg: { name: alg.name, curve: alg.curve },
      baseKeyTag: keyTags.get(baseKey) || 'untagged',
      secretB64: b64(bits), secretHexPrefix: hex(new Uint8Array(bits)),
    });
    return bits;
  }, origDerive);

  const origDeriveKey = subtle.deriveKey.bind(subtle);
  subtle.deriveKey = disguise(async function (alg, baseKey, derivedAlg, extractable, usages) {
    const key = await origDeriveKey(alg, baseKey, derivedAlg, extractable, usages);
    const tag = 'drv:' + (alg.name || '?') + '#' + LOG.length;
    keyTags.set(key, tag);
    rec({
      op: 'deriveKey', alg: safeAlg(alg), derivedAlg: safeAlg(derivedAlg),
      baseKeyTag: keyTags.get(baseKey) || 'untagged', tag,
    });
    return key;
  }, origDeriveKey);

  const origEncrypt = subtle.encrypt.bind(subtle);
  subtle.encrypt = disguise(async function (alg, key, plaintext) {
    const pU8 = new Uint8Array(plaintext);
    rec({
      op: 'encrypt',
      alg: { name: alg.name, iv: hex(alg.iv), additionalData: hex(alg.additionalData), tagLength: alg.tagLength },
      keyTag: keyTags.get(key) || 'untagged',
      plainLen: pU8.length, plainUtf8: utf8(pU8, 2000), plainB64: b64(pU8),
    });
    return origEncrypt(alg, key, plaintext);
  }, origEncrypt);

  const origDecrypt = subtle.decrypt.bind(subtle);
  subtle.decrypt = disguise(async function (alg, key, ciphertext) {
    const res = await origDecrypt(alg, key, ciphertext);
    const u8 = new Uint8Array(res);
    rec({
      op: 'decrypt', alg: { name: alg.name, iv: hex(alg.iv) },
      keyTag: keyTags.get(key) || 'untagged',
      cipherLen: u8.length, plainUtf8: utf8(u8, 4000), plainB64: b64(u8),
    });
    return res;
  }, origDecrypt);

  const origSign = subtle.sign.bind(subtle);
  subtle.sign = disguise(async function (alg, key, data) {
    const res = await origSign(alg, key, data);
    rec({
      op: 'sign', alg: safeAlg(alg), keyTag: keyTags.get(key) || 'untagged',
      dataUtf8: utf8(data, 1000), sigHex: hex(new Uint8Array(res)),
    });
    return res;
  }, origSign);

  const origDigest = subtle.digest.bind(subtle);
  subtle.digest = disguise(async function (alg, data) {
    const res = await origDigest(alg, data);
    rec({
      op: 'digest', alg: safeAlg(alg),
      dataUtf8: utf8(data, 500), hashHex: hex(new Uint8Array(res)), dataLen: data.byteLength,
    });
    return res;
  }, origDigest);

  // КРИТИЧНО: RTDL-крипто живёт ВНУТРИ SquareVM; ВМ достаёт примитивы
  // динамически (window['crypto']['subtle']). Подменяем геттеры, чтобы ловить
  // сам МОМЕНТ доступа ВМ к крипто-примитивам (кто, откуда, когда).
  ['crypto', 'Crypto', 'SubtleCrypto'].forEach((prop) => {
    try {
      const origDesc = Object.getOwnPropertyDescriptor(window, prop);
      if (!origDesc || !origDesc.get) return;
      Object.defineProperty(window, prop, {
        configurable: true,
        get: function () {
          let stack = '';
          try { stack = new Error().stack.split('\n').slice(1, 6).join(' | '); } catch (e) {}
          rec({ op: 'getterAccess', prop, stack });
          return origDesc.get.call(this);
        },
        set: origDesc.set,
      });
    } catch (e) {}
  });

  // ---------- 2. WebAssembly — слив модуля SquareVM -------------------------
  const dumpWasm = (bytes, where) => {
    const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    // НЕ кладём base64 всего модуля в rec()/LOG: сотни KB в памяти страницы +
    // сериализация через __HIJACK_DUMP__ убивали вкладку (OOM/обрыв CDP).
    // Полные байты лежат в __WASM_DUMPS__, раннер забирает их чанками.
    rec({ op: 'wasm', where, size: u8.length, magic: hex(u8.slice(0, 8)), b64preview: b64(u8.slice(0, 512)) });
    (window.__WASM_DUMPS__ = window.__WASM_DUMPS__ || []).push({ where, bytes: u8 });
  };

  // Headers-объект может ломать конструктор Response — приводим к plain-объекту
  const headersToObj = (h) => {
    try {
      if (!h) return {};
      if (typeof h.forEach === 'function') { const o = {}; h.forEach((v, k) => { o[k] = v; }); return o; }
      return Object.assign({}, h);
    } catch (e) { return {}; }
  };

  if (WebAssembly.instantiate) {
    const oi = WebAssembly.instantiate.bind(WebAssembly);
    WebAssembly.instantiate = disguise(async function (b, importObject) {
      dumpWasm(b, 'instantiate');
      if (importObject) {
        const imports = {};
        for (const mod of Object.keys(importObject)) imports[mod] = Object.keys(importObject[mod]);
        rec({ op: 'wasmImports', imports }); // кому ВМ доверяет crypto/случайность
      }
      const res = await oi(b, importObject);
      try { rec({ op: 'wasmExports', exports: Object.keys(res.instance.exports) }); } catch (e) {}
      return res;
    }, oi);
  }
  if (WebAssembly.instantiateStreaming) {
    const ois = WebAssembly.instantiateStreaming.bind(WebAssembly);
    WebAssembly.instantiateStreaming = disguise(async function (response, importObject) {
      const resp = await response;
      const buf = await resp.arrayBuffer();
      dumpWasm(buf, 'instantiateStreaming:' + (resp.url || '?'));
      let fresh;
      try {
        fresh = new Response(buf, { headers: headersToObj(resp.headers), status: resp.status, statusText: resp.statusText });
      } catch (e) {
        try { fresh = await fetch(resp.url); } catch (e2) { throw e; }
      }
      return ois(Promise.resolve(fresh), importObject);
    }, ois);
  }

  // ---------- 3. Сеть: привязка шифротекста к моменту encrypt() -------------
  const RG_RE = /linkvertise|getmadium|lootlabs|royalguard|pushToTalk|RTDL|PGPSC|PGPG|handshake/i;

  const ofetch = window.fetch;
  window.fetch = disguise(async function (input, init) {
    const url = typeof input === 'string' ? input
      : (input && typeof input.url === 'string' ? input.url : ((input && input.url) || '?'));
    // тело может лежать в Request-объекте, а не только в init — иначе теряем
    let body = init && init.body;
    if (body == null && input && typeof Request !== 'undefined' && input instanceof Request) {
      try { body = await input.clone().text(); } catch (e) {}
    }
    if (RG_RE.test(url)) {
      rec({
        op: 'fetch', url, method: (init && init.method) || (input && input.method) || 'GET',
        bodyHead: typeof body === 'string' ? body.slice(0, 500) : (body ? '[non-string]' : null),
      });
    }
    return ofetch.apply(this, arguments);
  }, ofetch);

  try {
    const oxhr = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = disguise(function (method, url) {
      if (RG_RE.test(String(url))) rec({ op: 'xhr', method, url: String(url) });
      return oxhr.apply(this, arguments);
    }, oxhr);
  } catch (e) {}

  const osb = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);
  if (osb) {
    navigator.sendBeacon = disguise(function (url, data) {
      rec({ op: 'sendBeacon', url, bodyHead: typeof data === 'string' ? data.slice(0, 500) : '[non-string]' });
      return osb.apply(this, arguments);
    }, osb);
  }

  // ---------- 4. Visibility/фокус — Royal Guard следит за этим (RTDL) -------
  ['visibilitychange', 'focus', 'blur', 'pagehide'].forEach((ev) => {
    try {
      document.addEventListener(ev, () => rec({ op: 'visibility', event: ev, state: document.visibilityState, focused: document.hasFocus() }), true);
    } catch (e) {}
  });

  // ---------- 5. Выгрузка собранного (использует раннер из Секции B) --------
  window.__HIJACK_DUMP__ = () => JSON.stringify(LOG, null, 1);
  window.__HIJACK_WASMS__ = () => (window.__WASM_DUMPS__ || []).map(w => ({ where: w.where, size: w.bytes.length }));
  window.__HIJACK_SAVEWASM__ = (i) => {
    const w = (window.__WASM_DUMPS__ || [])[i];
    if (!w) return;
    const blob = new Blob([w.bytes], { type: 'application/wasm' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'vm_' + String(w.where).replace(/[^a-z0-9]+/gi, '_') + '.wasm';
    a.click();
  };

  rec({ op: 'installed', ua: navigator.userAgent, href: location.href });
})();
`;

// ############################################################################
// ###                                                                      ###
// ###  СЕКЦИЯ B — CDP-РАННЕР (Node): attach ко всем вкладкам + запись      ###
// ###                                                                      ###
// ############################################################################

let CDP;
try { CDP = require('chrome-remote-interface'); }
catch (e) {
  console.error('Не хватает зависимости. Выполните:  npm i chrome-remote-interface');
  process.exit(1);
}

// --- конфигурация ------------------------------------------------------------
const PORT = parseInt(process.argv[2] || process.env.DEBUG_PORT || '9222', 10);
const AUTO_STOP_SEC = parseInt(process.env.RECORD_SEC || '0', 10); // 0 = до Ctrl-C
const DUMP_INTERVAL_MS = parseInt(process.env.DUMP_INTERVAL_MS || '10000', 10);
const MAX_BODY_BYTES = 1_500_000; // тела больше не сохраняем (защита от OOM)

const OUT_DIR = path.join(__dirname, '..', 'captures',
  'attach_' + new Date().toISOString().replace(/[:.]/g, '-'));
const SCRIPTS_DIR = path.join(OUT_DIR, 'scripts');
const RESP_DIR = path.join(OUT_DIR, 'responses');
const WASM_DIR = path.join(OUT_DIR, 'wasm');
for (const d of [OUT_DIR, SCRIPTS_DIR, RESP_DIR, WASM_DIR]) fs.mkdirSync(d, { recursive: true });

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

const RG_RE = /pushToTalk|PGPSC|PGPG|RTDL|handshake|linkvertise|getmadium|lootlabs|royalguard/i;

let reqCounter = 0;
const attached = new Set();      // targetId, к которым уже подключились
const clients  = [];             // живые CDP-клиенты
const dumpers  = [];             // периодические сборщики дампов
const savedWasm = new Set();     // targetId#idx — не сохранять один wasm дважды

// --- подключение к одному таргету ---------------------------------------------
async function attachToTarget(targetInfo) {
  const targetId = targetInfo && targetInfo.targetId;
  if (!targetId || attached.has(targetId)) return;
  attached.add(targetId);

  let client;
  try { client = await CDP({ port: PORT, target: targetId }); }
  catch (e) {
    log('не удалось подключиться к таргету', targetId, '-', String(e.message).slice(0, 120));
    attached.delete(targetId);
    return;
  }

  const { Network, Page, Runtime, Log } = client;

  // ГЛАВНОЕ: init-script внедряется ДО выполнения любого кода страницы —
  // перехватывается даже то, что выполняется на самых ранних этапах загрузки
  try {
    await Page.enable();
    await Page.addScriptToEvaluateOnNewDocument({ source: HIJACK_SRC });
  } catch (_) {}

  // ---- трафик: запросы ----
  const reqMap = new Map(); // requestId -> {id,url,type}
  await Network.enable().catch((e) => { log('Network.enable не удался:', e.message); });
  Network.requestWillBeSent(({ requestId, request, method, url, type, postData, initiator }) => {
    const id = ++reqCounter;
    reqMap.set(requestId, { id, url, type });
    write(tStream, { dir: 'req', id, ts: stamp(), method, url, type,
      headers: request.headers, postData: (postData || '').slice(0, 4000),
      initiator: initiator && initiator.type, target: targetId });
    if (RG_RE.test(url)) event('RG-ENDPOINT', { id, url });
  });

  // ---- трафик: ответы ----
  Network.responseReceived(({ requestId, response }) => {
    const meta = reqMap.get(requestId);
    write(tStream, { dir: 'resp', id: meta && meta.id, ts: stamp(), status: response.status,
      url: response.url, type: response.type, headers: response.headers, target: targetId });
  });

  // ---- трафик: тела (исходники в scripts/, RG-эндпоинты в responses/) ----
  Network.loadingFinished(async ({ requestId }) => {
    const meta = reqMap.get(requestId);
    if (!meta) return;
    try {
      const { body, base64Encoded } = await Network.getResponseBody({ requestId });
      const buf = base64Encoded ? Buffer.from(body, 'base64') : Buffer.from(body, 'utf8');
      if (buf.length > MAX_BODY_BYTES) return;
      const name = `${String(meta.id).padStart(4, '0')}_${String(meta.url).replace(/[^a-zA-Z0-9.-]+/g, '_').slice(-90)}.js`;
      if (meta.type === 'Script' || /\.js(\?|$)/i.test(meta.url) || RG_RE.test(meta.url)) {
        fs.writeFileSync(path.join(RG_RE.test(meta.url) ? RESP_DIR : SCRIPTS_DIR, name), buf);
      }
    } catch (_) {}
    // wasm-модуль SquareVM мог прийти обычным fetch/arraybuffer — как только
    // страница его инстанцирует, hijack положит байты в __WASM_DUMPS__;
    // забираем их на диск сразу после окончания загрузки ресурсов
    setTimeout(() => saveWasmDumps(client, targetId).catch(() => {}), 1500);
  });

  // ---- консоль страницы (Log domain надёжнее Runtime при плотном логе) ----
  try {
    await Log.enable();
    Log.on('entryAdded', ({ entry }) => event(`console:${entry.level}`, { text: entry.text, source: entry.url }));
  } catch (_) {}

  // ---- runtime-события + прямой канал hijack-записей ----
  await Runtime.enable().catch((e) => { log('Runtime.enable не удался:', e.message); });
  Runtime.on('consoleAPICalled', ({ type, args }) => {
    const text = (args || []).map(a => a.value !== undefined ? String(a.value) : (a.description || a.type)).join(' ');
    event(`runtime:${type}`, { text });
    if (text.startsWith('[HIJACK]')) cStream.write(text.slice('[HIJACK]'.length).trim() + '\n');
  });
  // binding = основной канал crypto.jsonl (не зависит от усечений консоли)
  await Runtime.addBinding({ name: '__hijack_send' }).catch(() => {});
  Runtime.on('bindingCalled', ({ name, payload }) => {
    if (name === '__hijack_send') cStream.write(payload + '\n');
  });

  clients.push(client);
  client.on('destroyed', () => { attached.delete(targetId); });
  client.on('error',     () => { attached.delete(targetId); });
  log('+ таргет:', targetId, '-', (targetInfo.url || '').slice(0, 100));

  // Если подключаемся к УЖЕ загруженной живой вкладке, init-script сработает
  // только на следующую навигацию — поэтому догружаем hijack в текущий
  // документ немедленно (binding уже объявлен выше → канал работает сразу).
  try { await Runtime.evaluate({ expression: HIJACK_SRC, includeCommandLineAPI: false }); } catch (_) {}

  // периодический страхующий сбор полного дампа + wasm
  dumpers.push(async () => {
    try {
      const { result } = await Runtime.evaluate({
        expression: 'window.__HIJACK_DUMP__ ? window.__HIJACK_DUMP__() : ""', returnByValue: true });
      if (result && result.value) {
        try { JSON.parse(result.value).forEach(o => cStream.write(JSON.stringify(o) + '\n')); }
        catch (_) { cStream.write(result.value + '\n'); }
      }
    } catch (_) {}
    await saveWasmDumps(client, targetId);
  });
}

// --- выгрузка дампов wasm-модулей из страницы на диск --------------------------
async function saveWasmDumps(client, targetId) {
  try {
    const { result } = await client.Runtime.evaluate({
      expression: '(window.__WASM_DUMPS__||[]).map(w=>({where:w.where,size:w.bytes.length}))',
      returnByValue: true });
    const list = (result && result.value) || [];
    for (let i = 0; i < list.length; i++) {
      const key = targetId + '#' + i;
      if (savedWasm.has(key)) continue;
      savedWasm.add(key);
      const parts = [];
      const CHUNK = 256 * 1024; // ~341KB base64 на чанк — безопасно для CDP
      let ok = true;
      for (let off = 0; off < list[i].size; off += CHUNK) {
        const r = await client.Runtime.evaluate({
          expression: `(()=>{const u=(window.__WASM_DUMPS__||[])[${i}];if(!u)return '';return btoa(String.fromCharCode.apply(null,u.bytes.subarray(${off},${off + CHUNK})))})()`,
          returnByValue: true });
        const p = r && r.result && r.result.value;
        if (!p && list[i].size > 0) { ok = false; break; }
        parts.push(p || '');
      }
      if (ok && parts.length) {
        const name = `${targetId.slice(0, 8)}_${String(list[i].where).replace(/[^a-zA-Z0-9.-]+/g, '_').slice(-60)}.wasm`;
        fs.writeFileSync(path.join(WASM_DIR, name), Buffer.from(parts.join(''), 'base64'));
        log('+ wasm-дамп сохранён:', name, `(${list[i].size} байт)`);
        event('WASM-SAVED', { file: name, size: list[i].size, where: list[i].where });
      }
    }
  } catch (_) {}
}

// --- главный цикл ----------------------------------------------------------------
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
      `и уже в нём открывай нужный сайт (Royal Guard / linkvertise-промежуточки).`);
    process.exit(1);
  }

  // подключаемся ко ВСЕМ уже открытым page-таргетам
  for (const t of tabs) if (t.type === 'page') await attachToTarget(t);

  // и автоматически отслеживаем НОВЫЕ вкладки, открываемые по ходу «промежуточков»
  const browser = await CDP({ port: PORT });
  await browser.Target.setDiscoverTargets({ discover: true });
  browser.Target.on('targetCreated', async ({ targetInfo }) => {
    if (targetInfo.type === 'page') await attachToTarget(targetInfo);
  });

  event('SESSION-START', { mode: 'attach', port: PORT, targets: attached.size });
  log(`Пишу всё в: ${OUT_DIR}`);
  log(`Подключено вкладок: ${attached.size}. Кликай по сайту. Останов — Ctrl-C.` +
      (AUTO_STOP_SEC ? ` (автостоп через ${AUTO_STOP_SEC}с)` : ''));

  const iv = setInterval(() => dumpers.forEach(f => f().catch(() => {})), DUMP_INTERVAL_MS);

  let stopping = false;
  async function stop(sig) {
    if (stopping) return; stopping = true;
    clearInterval(iv);
    event('SESSION-END', { requests: reqCounter, sig: sig || 'auto' });
    // финальный сбор hijack-дампа со всех вкладок
    for (const f of dumpers) { try { await f(); } catch (_) {} }
    // структурированный итоговый дамп — первая вкладка, где он непустой
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
