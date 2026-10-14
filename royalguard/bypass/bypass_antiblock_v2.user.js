// ==UserScript==
// @name         linkvertise.lol DTOM/VGuard bypass (v2)
// @namespace    local-analysis
// @version      2.0
// @description  Полноценный обход DTOM-холдинга и VGuard-интерстишала на kys.linkvertise.lol.
//               Методы взяты из кода самого сайта (window.io20 в 0018/0019, proceed() в 0019).
//               v2 исправляет v1: не трогает /TaskStarted/, если сервер сам вернул captcha/adblock,
//               корректно кликает реальные кнопки, жрёт только adblock-beacon, имеет fallback.
// @match        *://kys.linkvertise.lol/*
// @match        *://*.linkvertise.lol/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(() => {
    'use strict';

    const log = (...a) => console.log('[bypass-v2]', ...a);
    const url = location.href;

    // ------------------------------------------------------------------
    // 0) Защита от бесконечного редиректа: если мы УЖЕ на TaskStarted,
    //    ничего сами не трогаем — сервер сам решит, нужен ли CaptchaTicket.
    //    (В v1 это было причиной "не получилось": слепой повторный заход
    //     без капчи зацикливал страницу.)
    // ------------------------------------------------------------------
    // Все хелперы объявляем ДО ранних return'ов (в v1 здесь была TDZ-ошибка:
    // const BTN_SELECTORS использовался до инициализации) — сначала hoisting-функции.
    function genUuid() {
        try { return crypto.randomUUID(); } catch (_) {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
                const r = Math.random() * 16 | 0;
                return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
            });
        }
    }

    function onReady(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    // Кнопки именно те, что рендерит сайт: continue-box / retry-btn (см. 0018/0019)
    const BTN_SELECTORS = [
        '#continue-box .btn', '#continue-box button',
        '[id*="continue"] button', 'button.btn',
    ];
    let forcedOnce = false;

    function clickContinue() {
        for (const sel of BTN_SELECTORS) {
            const b = document.querySelector(sel);
            if (b && !b.disabled && b.offsetParent !== null) {
                log('clicking', sel); b.click(); return true;
            }
        }
        return false;
    }

    function autoClickNow() {
        if (clickContinue()) return;
        const mo = new MutationObserver(() => {
            if (clickContinue()) mo.disconnect();
        });
        try { mo.observe(document.body, { childList: true, subtree: true }); } catch (_) {}
        setTimeout(() => {
            mo.disconnect();
            // финальный запасной выход: прямой proceed по авторскому методу
            if (!forcedOnce && !/\/TaskStarted\//i.test(location.href)) {
                forcedOnce = true;
                log('last-resort author bypass');
                location.replace(location.href.replace('DTOM', 'TaskStarted') + '&CA=' + genUuid());
            }
        }, 8000);
    }

    if (/\/TaskStarted\//i.test(url)) {
        log('already on TaskStarted — passive mode');
        // Пассивно: подстрахуем кнопку Continue, если она появится после капчи.
        onReady(autoClickNow);
        return;
    }

    // ------------------------------------------------------------------
    // 1) Главный хоп: /DTOM/<uuid> -> /TaskStarted/<uuid>&CA=<uuid>
    //    Дословный авторский метод (window.io20):
    //    location.href.replace('DTOM','TaskStarted')+'&CA='+crypto.randomUUID()
    // ------------------------------------------------------------------
    if (/\/DTOM\/[0-9a-f-]{36}/i.test(url)) {
        const uuid = (url.match(/\/DTOM\/([0-9a-fA-F-]{36})/) || [])[1];
        if (uuid) {
            let dest;
            try {
                dest = url.replace('DTOM', 'TaskStarted') + '&CA=' + crypto.randomUUID();
            } catch (_) {
                // crypto.randomUUID недоступен в небезопасном контексте — ручной UUID v4
                dest = url.replace('DTOM', 'TaskStarted') + '&CA=' +
                    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
                        const r = Math.random() * 16 | 0;
                        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
                    });
            }
            log('DTOM -> TaskStarted:', dest);
            location.replace(dest);
            return;
        }
    }

    // ------------------------------------------------------------------
    // 2) Ждём DOM и читаем переменные страницы (NEXT_HREF и флаги заданы
    //    инлайн-скриптом сайта в <head>/<body>, см. 0018/0019 строка 1).
    //    Это надёжнее, чем выдумывать selectors: берём те же id, что сайт.
    //    Все хелперы (genUuid/onReady/clickContinue/autoClickNow) уже
    //    объявлены выше — здесь только логика ветвления.
    // ------------------------------------------------------------------
    onReady(() => {
        const NEXT = window.NEXT_HREF ||
            (document.documentElement.innerHTML.match(/NEXT_HREF\s*=\s*"([^"]+)"/) || [])[1];

        // 2a) Если сервер сказал NEEDS_CPT=true — капча обязательна,
        //     НЕ трогаем proceed(), иначе получаем ошибку «не получилось».
        const needsCpt = /NEEDS_CPT\s*=\s*true/.test(document.documentElement.innerHTML);

        // 2b) HAS_ADS=false у этого сайта (ADS_SCRIPT_URL=null) →
        //     штатный путь сайта: setTimeout(proceed, 180) с той же NEXT_HREF.
        //     Идём тем же путём, но сразу, минуя паузы/проверки.
        if (!needsCpt && NEXT && /TaskStarted/i.test(NEXT)) {
            log('proceed via site-owned NEXT_HREF:', NEXT);
            location.replace(NEXT + (NEXT.includes('?') ? '&' : '?') + 'CA=' + genUuid());
            return;
        }

        // 2c) Страница VGuard-интерстишала (0025 делает location.replace
        //     на /VMc/VGuard_v1?TID=...&TAD=...). TAD генерится ВМ на клиенте,
        //     серверной проверки нет → просто не даём уйти на VMc и идём дальше.
        if (/VMc|VGuard/i.test(url)) {
            log('on VMc page — skipping to next');
            if (NEXT) location.replace(NEXT + '&CA=' + genUuid());
            return;
        }

        // 2d) Fallback: любой экран с кнопкой Continue — кликаем по id сайта.
        autoClickNow();
    });

    // ------------------------------------------------------------------
    // 3) Beacon /DTOM/<uuid>/adblock {d:0|1} — подменяем ТОЛЬКО d:1 на d:0.
    //    В v1 он проглатывался целиком; лучше честно рапортовать чистоту,
    //    т.к. сервер помнит состояние задачи.
    // ------------------------------------------------------------------
    const realBeacon = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);
    if (realBeacon) {
        navigator.sendBeacon = function (u, data) {
            try {
                if (String(u).includes('/adblock')) {
                    return realBeacon(u, JSON.stringify({ d: 0 }));
                }
            } catch (_) {}
            return realBeacon(u, data);
        };
    }
    const realFetch = window.fetch && window.fetch.bind(window);
    if (realFetch) {
        window.fetch = function (input, init) {
            try {
                const u = typeof input === 'string' ? input : (input && input.url) || '';
                if (u.includes('/adblock')) {
                    init = Object.assign({}, init || {}, { body: JSON.stringify({ d: 0 }) });
                }
            } catch (_) {}
            return realFetch(input, init);
        };
    }

    // ------------------------------------------------------------------
    // 4) Анти-зависание: если через 12 сек всё ещё на холдинг-экране
    //    и есть NEXT_HREF — форсируем переход один раз.
    // ------------------------------------------------------------------
    let forced = false;
    setTimeout(() => {
        if (forced || /\/TaskStarted\//i.test(location.href)) return;
        const m = document.documentElement.innerHTML.match(/NEXT_HREF\s*=\s*"([^"]+)"/);
        if (m && /TaskStarted/i.test(m[1])) {
            forced = true;
            log('fallback force redirect');
            location.replace(m[1] + '&CA=' + genUuid());
        }
    }, 12000);
})();
