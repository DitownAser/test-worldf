[Обход DTOM/VGuard на kys.linkvertise.lol — v2]

Файлы:
  bypass_antiblock_v2.user.js  — РАБОЧАЯ версия (Violentmonkey/Tampermonkey/Userscripts)
  bypass_antiblock.user.js     — старая v1, НЕ использовать (см. список багов ниже)

Почему v1 «сразу выдавало ошибку» (разбор по коду сайта):
  1. В захваченном HTML DTOM-страницы (файлы 0018/0019 репо) элемента #continue-box
     НЕТ в разметке — его показывает только JS showContinue(). Клик по несуществующей
     кнопке ничего не давал, страница оставалась на «Verifying your browser».
  2. Слепой редирект DTOM->TaskStarted без проверки NEEDS_CPT: если сервер для твоего
     IP требовал капчу, повторный заход отбрасывался обратно → «не получилось».
  3. crypto.randomUUID() кидает исключение в небезопасном контексте (http://) — v1 падал.
  4. history.pushState + defineProperty в мёртвом коде вызывали ошибки в консоли.
  5. TDZ-ошибка (const использовался до объявления) при раннем return.

Что делает v2 (все методы взяты из кода самого сайта):
  - /DTOM/<uuid> -> /TaskStarted/<uuid>&CA=<uuid> — дословный авторский метод (window.io20);
  - читает NEXT_HREF прямо со страницы и идёт штатным путём proceed() сайта,
    НО только если NEEDS_CPT=false (иначе капча обязательна — обход её не отменяет);
  - фоллбэк-UUID если crypto.randomUUID недоступен;
  - подмена adblock-beacon {d:1} -> {d:0} (sendBeacon И fetch), а не проглатывание;
  - автоклик реально существующих кнопок + last-resort редирект через 8 сек;
  - защита от циклов: на /TaskStarted/ работает пассивно.

Установка: Violentmonkey -> «+» -> вставить содержимое bypass_antiblock_v2.user.js.

Проверено локально: node --check ОК; harness-тесты (эмуляция DTOM-страницы):
  A) DTOM-URL -> корректный TaskStarted+CA          PASS
  B) уже на TaskStarted -> ноль редиректов (пассив) PASS
  C) NEXT_HREF из innerHTML -> proceed с CA          PASS

uBlock Origin (альтернатива без скриптов):
  ||kys.linkvertise.lol/VMc/$doc,domain=kys.linkvertise.lol
  ||kys.linkvertise.lol/api/rg/$xhr,domain=kys.linkvertise.lol

Примечание: если сервер вернул страницу с капчей (NEEDS_CPT=true) — ни один обход
её не снимает, капча решается руками; после неё Continue работает сам.
