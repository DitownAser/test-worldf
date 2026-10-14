// ============================================================================
// crypto_hijack.js — перехват криптографических примитивов в реальном времени
// Цель: не реверсить SquareVM целиком, а "подслушать" её на границе с браузером:
//   1) SubtleCrypto (AES-GCM/X25519/HMAC/SHA) — ключи, IV, plaintext RTDL
//   2) WebAssembly.instantiate* — вытащить .wasm-модуль ВМ на диск
//   3) fetch/XHR/SendBeacon — связать каждый шифротекст с его plaintext/ключом
//
// Как использовать (2 варианта):
//
// A) Через существующий CDP-пайплайн (captures/ собирался так же):
//    node cdp_run.js   # см. hijack_attach.js рядом — он подключается к Chrome
//    и вызывает attach(pageClient, 'crypto_hijack.js') ДО навигации на kys.linkvertise.lol
//
// B) Вручную: chrome://snippets или DevTools → Sources → Snippets,
//    но ВАЖНО: код должен быть исполнен ДО загрузки страницы (init script),
//    иначе ВМ уже сохранит себе ссылки на нативные функции (native-pinning).
//    Для B лучше через Page.addScriptToEvaluateOnNewDocument (см. hijack_attach.js).
//
// Анти-anti-debug замечания:
//  - Не используем debugger statements и не трогаем Function.prototype.toString
//    до тех пор, пока сами не будем вызваны; все обёртки сохраняют toString
//    через WeakMap подмены (см. disguise()).
//  - Если ВМ проверяет целостность window.crypto.subtle через toString(),
//    disguise() вернёт ей "нативный" вид.
// ============================================================================

(function () {
  'use strict';
  if (window.__HIJACK_INSTALLED__) return;
  window.__HIJACK_INSTALLED__ = true;

  const LOG = [];
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
  const rec = (obj) => {
    obj.t = now();
    LOG.push(obj);
    // дублируем в консоль — CDP-логгер captures/ подхватит console.* сам
    console.log('[HIJACK]', JSON.stringify(obj));
  };

  // --- маскировка обёрток: native toString ---------------------------------
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

  // =========================================================================
  // 1. SubtleCrypto: AES-GCM encrypt/decrypt, deriveBits, HMAC, digest
  //    Это самый ценный перехват: на входе decrypt() серверного ответа и
  //    выходе encrypt() пакетов pushToTalk мы получаем УЖЕ ГОТОВЫЙ plaintext
  //    RTDL — без единой инструкции из байткода SquareVM.
  // =========================================================================
  const subtle = crypto.subtle;

  const wrapMethod = (obj, name, before, after) => {
    const orig = obj[name].bind(obj);
    const wrapped = async function (...args) {
      let ctx;
      try { ctx = before && before(args); } catch (e) {}
      const res = await orig(...args);
      try { after && after(args, res, ctx); } catch (e) {}
      return res;
    };
    return disguise(Object.defineProperty(wrapped, 'name', { value: name }), orig);
  };

  // Ключевые объекты CryptoKey непрозрачны — храним "метки", которые сами
  // присваиваем при generate/import/derive, чтобы потом в encrypt() видеть
  // "какой ключ откуда".
  const keyTags = new WeakMap();

  const origGenerate = subtle.generateKey.bind(subtle);
  subtle.generateKey = disguise(async function (alg, extractable, usages) {
    const key = await origGenerate(alg, extractable, usages);
    const tag = 'gen:' + (alg.name || '?') + ':' + (alg.namedCurve || alg.length || '') + '#' + LOG.length;
    keyTags.set(key, tag);
    if (key.privateKey) keyTags.set(key.privateKey, tag + '/priv');
    if (key.publicKey) keyTags.set(key.publicKey, tag + '/pub');
    rec({ op: 'generateKey', alg, tag });
    return key;
  }, origGenerate);

  const origImport = subtle.importKey.bind(subtle);
  subtle.importKey = disguise(async function (format, keyData, alg, extractable, usages) {
    const key = await origImport(format, keyData, alg, extractable, usages);
    const tag = 'imp:' + format + ':' + (alg.name || '?');
    keyTags.set(key, tag);
    rec({
      op: 'importKey', format, alg,
      dataHex: typeof keyData === 'string' ? keyData.slice(0, 64) : hex(keyData),
      dataFullB64: typeof keyData !== 'string' ? b64(keyData) : null,
      tag,
    });
    return key;
  }, origImport);

  const origDerive = subtle.deriveBits.bind(subtle);
  subtle.deriveBits = disguise(async function (alg, baseKey, length) {
    const bits = await origDerive(alg, baseKey, length);
    // ECDH(X25519)-секрет = общий секрет RTDL-туннеля "YX". Ловим его здесь.
    rec({
      op: 'deriveBits', alg: { name: alg.name, curve: alg.curve },
      baseKeyTag: keyTags.get(baseKey) || 'untagged',
      secretB64: b64(bits), secretHexPrefix: hex(new Uint8Array(bits)),
    });
    // если alg содержит salt/info (HKDF) — тоже записываем
    return bits;
  }, origDerive);

  const origDeriveKey = subtle.deriveKey.bind(subtle);
  subtle.deriveKey = disguise(async function (alg, baseKey, derivedAlg, extractable, usages) {
    const key = await origDeriveKey(alg, baseKey, derivedAlg, extractable, usages);
    const tag = 'drv:' + (alg.name || '?') + '#' + LOG.length;
    keyTags.set(key, tag);
    rec({
      op: 'deriveKey', alg, derivedAlg,
      baseKeyTag: keyTags.get(baseKey) || 'untagged', tag,
    });
    return key;
  }, origDeriveKey);

  const origEncrypt = subtle.encrypt.bind(subtle);
  subtle.encrypt = disguise(async function (alg, key, plaintext) {
    const pU8 = new Uint8Array(plaintext);
    rec({
      op: 'encrypt', alg: { name: alg.name, iv: hex(alg.iv), additionalData: hex(alg.additionalData), tagLength: alg.tagLength },
      keyTag: keyTags.get(key) || 'untagged',
      plainLen: pU8.length,
      plainUtf8: (() => { try { return new TextDecoder().decode(pU8).slice(0, 2000); } catch (e) { return null; } })(),
      plainB64: b64(pU8),
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
      cipherLen: u8.length,
      plainUtf8: (() => { try { return new TextDecoder().decode(u8).slice(0, 4000); } catch (e) { return null; } })(),
      plainB64: b64(u8),
    });
    return res;
  }, origDecrypt);

  const origSign = subtle.sign.bind(subtle);
  subtle.sign = disguise(async function (alg, key, data) {
    const res = await origSign(alg, key, data);
    rec({
      op: 'sign', alg, keyTag: keyTags.get(key) || 'untagged',
      dataUtf8: (() => { try { return new TextDecoder().decode(data).slice(0, 1000); } catch (e) { return null; } })(),
      sigHex: hex(new Uint8Array(res)),
    });
    return res;
  }, origSign);

  // КРИТИЧНО: RTDL-крипто живёт ВНУТРИ SquareVM (в inline-скрипте 0024 нет строк
  // "subtle"/"WebAssembly" — значит ВМ достаёт crypto.subtle динамически через
  // window['crypto']['subtle'] и т.п.). Поэтому подменяем геттеры, чтобы ловить
  // сам МОМЕНТ доступа ВМ к примитивам (кто, откуда, когда).
  const accessLog = [];
  ['crypto', 'Crypto', 'SubtleCrypto'].forEach((prop) => {
    try {
      const origDesc = Object.getOwnPropertyDescriptor(window, prop);
      if (!origDesc || !origDesc.get) return;
      Object.defineProperty(window, prop, {
        configurable: true,
        get: function () {
          let stack = '';
          try { stack = new Error().stack.split('\n').slice(1, 6).join(' | '); } catch (e) {}
          accessLog.push({ t: now(), prop, stack });
          rec({ op: 'getterAccess', prop, stack });
          return origDesc.get.call(this);
        },
        set: origDesc.set,
      });
    } catch (e) {}
  });

  const origDigest = subtle.digest.bind(subtle);
  subtle.digest = disguise(async function (alg, data) {
    const res = await origDigest(alg, data);
    rec({
      op: 'digest', alg,
      dataUtf8: (() => { try { return new TextDecoder().decode(data).slice(0, 500); } catch (e) { return null; } })(),
      hashHex: hex(new Uint8Array(res)),
      dataLen: data.byteLength,
    });
    return res;
  }, origDigest);

  // =========================================================================
  // 2. WebAssembly — слив самого модуля SquareVM (.wasm) на страницу
  //    Модуль приходит по fetch как ArrayBuffer; instantiate принимает его
  //    напрямую. Хватаем bytes + экспортную таблицу + импортные импорты
  //    (JS-функции, которым ВМ доверяет crypto — это и есть "граница").
  // =========================================================================
  const dumpWasm = (bytes, where) => {
    const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const magic = hex(u8.slice(0, 8));
    rec({ op: 'wasm', where, size: u8.length, magic, b64: b64(u8) });
    // дополнительно: сохранить в IndexedDB-free способ — просто глобал для выгрузки
    (window.__WASM_DUMPS__ = window.__WASM_DUMPS__ || []).push({ where, bytes: u8 });
  };

  if (WebAssembly.instantiate) {
    const oi = WebAssembly.instantiate.bind(WebAssembly);
    WebAssembly.instantiate = disguise(async function (b, importObject) {
      dumpWasm(b, 'instantiate');
      // логируем имена импортных функций — кто даёт ВМ crypto/случайность
      if (importObject) {
        const imports = {};
        for (const mod of Object.keys(importObject)) {
          imports[mod] = Object.keys(importObject[mod]);
        }
        rec({ op: 'wasmImports', imports });
      }
      const res = await oi(b, importObject);
      try {
        rec({ op: 'wasmExports', exports: Object.keys(res.instance.exports) });
      } catch (e) {}
      return res;
    }, oi);
  }
  if (WebAssembly.instantiateStreaming) {
    const ois = WebAssembly.instantiateStreaming.bind(WebAssembly);
    WebAssembly.instantiateStreaming = disguise(async function (response, importObject) {
      // буферизуем ответ, чтобы слить байты, и пересоздаём Response
      const resp = await response;
      const buf = await resp.arrayBuffer();
      dumpWasm(buf, 'instantiateStreaming:' + (resp.url || '?'));
      const fresh = new Response(buf, { headers: resp.headers, status: resp.status });
      return ois(Promise.resolve(fresh), importObject);
    }, ois);
  }

  // =========================================================================
  // 3. Сеть: привязываем каждый yx_cipher/pushToTalk к моменту encrypt()
  //    (по времени t и по телу запроса). Позволяет офлайн-сборкой:
  //    plaintext <-> ciphertext <-> keyTag -> полная расшифровка архива.
  // =========================================================================
  const ofetch = window.fetch;
  window.fetch = disguise(async function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '?';
    const body = init && init.body;
    if (/linkvertise|getmadium|lootlabs/.test(url)) {
      rec({
        op: 'fetch', url, method: (init && init.method) || 'GET',
        bodyHead: typeof body === 'string' ? body.slice(0, 500) : (body ? '[non-string]' : null),
      });
    }
    return ofetch.apply(this, arguments);
  }, ofetch);

  const osb = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);
  if (osb) {
    navigator.sendBeacon = disguise(function (url, data) {
      rec({ op: 'sendBeacon', url, bodyHead: typeof data === 'string' ? data.slice(0, 500) : '[non-string]' });
      return osb.apply(this, arguments);
    }, osb);
  }

  // =========================================================================
  // Выгрузка собранного (запускать из консоли/CDP после сессии)
  // =========================================================================
  window.__HIJACK_DUMP__ = () => JSON.stringify(LOG, null, 1);
  window.__HIJACK_WASMS__ = () => (window.__WASM_DUMPS__ || []).map(w => ({ where: w.where, size: w.bytes.length }));
  // скачивание дампа wasm: window.__HIJACK_SAVEWASM__(0)
  window.__HIJACK_SAVEWASM__ = (i) => {
    const w = (window.__WASM_DUMPS__ || [])[i];
    if (!w) return;
    const blob = new Blob([w.bytes], { type: 'application/wasm' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'vm_' + w.where.replace(/[^a-z0-9]+/gi, '_') + '.wasm';
    a.click();
  };

  rec({ op: 'installed', ua: navigator.userAgent });
})();
