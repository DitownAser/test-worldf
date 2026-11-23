# Система сертификатов в GTNH Extra Nerf — полный разбор

Пакет: `pl.kuba6000.gtnhextranerf.progression` (+ подпакет `exam`, mixin'ы в `mixins.late`).
Это «прогрессия через допуски»: мир не может использовать машины следующего вольтажа, пока игрок
не получит **сертификат** (предмет) и не активирует его; сертификат хранится как глобальный флаг мира.

## 1. Уровни (ProgressionTier)

Энум из 15 тиров, каждый с полями: `id` (строка), `bit` (битовая маска), `prerequisite`, `hasExam`, текстура.

```
STEAM, LV, MV, HV, EV, IV, LuV, ZPM, UV, UHV, UEV, UIV, UMV, UXV, MAX
```

- `REQUIRED_MASK` / `requiredMask(tier)` — битовая маска всех обязательных предшествующих сертификатов
  («более ранние сертификаты должны оставаться действительными» — прямо так в lang-строках).
- Экзамен (`hasExam()`) есть только у LV: «OSHA Electrical Safety Exam». Начиная с MV получение —
  «заплати пошлину, без экзамена» (`Pay the fee to certify this world. No exam required.`).
  У STEAM — отдельный путь/предмет `steam_certificate` (своя ветка SteamSafety/MixinSteamMultiBlock).

## 2. Хранение состояния мира — ProgressionData (WorldSavedData)

Класс наследует `net.minecraft.world.WorldSavedData`, имя записи: **`gtnhextranerf_progression`**.

Поля:
| Поле | Тип | NBT-ключ | Назначение |
|---|---|---|---|
| `unlockedMask` | int (битовая маска тиров) | `certifiedTiers` {tierId: true} | какие тиры сертифицированы в мире |
| `certificateEpochs` | Map<Tier, Long> | `certificateEpochs` {tierId: long} | «эпоха выдачи» каждого сертификата — счётчик переизданий |
| `telemetryBlocked` | boolean | `telemetryBlocked` | анти-чит флаг (см. п.7) |

Методы (по байткоду):
- `unlock(tier)` — ставит бит `tier.bit()` в `unlockedMask`, `markDirty()`. Возвращает false, если уже стоит.
- `revoke(tier)` — снимает бит И **инкрементирует epoch** этого тира (`epoch+1`) → все ранее выданные
  предметы-сертификаты этого тира становятся просроченными.
- `certificateEpoch(tier)` / `isCurrentCertificate(tier, epoch)` — сравнение epoch предмета с текущей эпохой мира.

## 3. Предмет-сертификат — ProgressionCertificateItem + ProgressionCertificates

- Каждый тир регистрирует свой предмет (`lv_certificate`, `mv_certificate`, …, текстур
  `progression_certificate.png` / `..._warning.png`, `steam_certificate.png`).
- **Выдача** `ProgressionCertificates.issue(world, tier)`:
  создаёт ItemStack и кладёт в NBT тег **`gtnhextranerf_certificate_epoch`** =
  `MachineProgression.certificateEpoch(world, tier)` — т.е. предмет «подписан» текущей эпохой мира.
- **Активация** (`onItemRightClick`/func_77659_a, только сервер, предмет в активной руке):
  1. `issuedEpoch(stack)` читает тег (нет NBT → 0).
  2. Если `!MachineProgression.isCurrentCertificate(world, tier, epoch)` → чат
     `gtnhextranerf.progression.expired_certificate` («%s has expired. Pass its exam again…») — предмет НЕ расходуется.
  3. Иначе `certify(world, tier)`; при успехе и не creative — stack.size-- (предмет расходуется на активации).
- Так реализована защита от «выдал себе сертификат в креативе / скопировал через give»: фальшивый или
  старый (до revoke) сертификат не примется, потому что epoch не совпадает с миром.

## 4. MachineProgression — бизнес-логика блокировки машин

- `requiredTier(MetaTileEntity)` — по машине определяет нужный сертификат: реализация интерфейса
  `ProgressionMachine.requiredCertificate()`, либо для базовых электрических машин GregTech — по максимальному
  тиру энергетического хаба (`maxEnergyHatchTier`), есть исключения (Industrial Apiary, Crop Manager).
- `isLocked(mte)` (байткод):
  ```java
  tier = requiredTier(mte); if (tier == null) return false;
  world = worldOf(mte);     if (world == null) return true;    // нет мира → заблокировать
  if (world.isRemote) return false;                            // клиент никогда не «знает»
  return data(world).isMissing(tier);                          // бит не выставлен → locked
  ```
- `missingTier(mte)` — какой именно сертификат отсутствует (для подсказок/GUI).
- `certify/isCertified/revoke/certificateEpoch/isCurrentCertificate` — тонкие обёртки над ProgressionData.
- В `certify()` дополнительно: если тир имеет экзамен и мир к моменту сертификации прожил меньше
  `TelemetryEligibility.MINIMUM_WORLD_TICKS` (**5 игровых часов**, 5*1200*20 тиков) — вызывается
  `blockTelemetry()`: лог «Telemetry is off for this world for good: the {} certificate was earned before
  the world had run 5 hours». Это анти-спидран-флаг: такие миры теряют право на телеметрию.

## 5. Как блокировка внедряется в GregTech (Mixin'ы late-стадии)

- **MixinProgressionTickGate** (wrapOperation на tick BaseMetaTileEntity): если сервер и `isLocked(mte)` →
  `setActive(false)` и операция пропускается (машина не работает); при снятии блокировки вызывается
  `onFirstTick/func_70296_d` для корректного «размороза». Флаг `gtnhextranerf$wasCertificationLocked`
  отслеживает переходы.
- **MixinMultiblockCertification**: после проверки структуры мультиблока, если `isLocked` → `setActive(false)`
  + cancel — мультиблок собирается, но не стартует без сертификата.
- **EnergyHatchCertification** (события Forge):
  - `onPlaced` — при установке незакрытого энергетического/динамо хаба без лицензии — предупреждение.
  - `onInteract` — ПКМ по залоченному хабу → чат `gtnhextranerf.progression.hatch.disabled`
    с кликабельной кнопкой `[Open certification]`, которая выполняет команду `/extranerf-certificate <tier>`
    (класс `OpenCertificateCommand`, уровень прав 2? — `func_82362_a`).
  - Хуки `PortHook/BufferHook/WirelessInputHook` + **MixinWirelessHatchCertification / MixinWirelessCoverCertification**
    (`gtnhextranerf$noUnlicensedWithdrawal` — cancel): без сертификата нельзя снимать энергию через
    wireless hatch/cover — «no unlicensed withdrawal».
- **MixinSteamMultiBlock / MixinSteamMachineGui / MixinSteamMachineDisplay** — аналогично для Steam-тира
  (параллельная ветка прогрессии с `steam_certificate`).
- GUI: `CertificateStatusWidget`/`CertificateStatusPanel` (модулярное UI) показывают в машине статус
  сертификата (иконки warning), клик открывает экзамен/получение.

## 6. Получение сертификата: экзамен (LV) и пошлина (MV+)

Подпакет `progression.exam`:

- **CertificationExams** — реестр: для каждого тира с `hasExam()` регистрируется GUI-фабрика
  `gtnhextranerf.<tier>_exam`; определения берутся из `BundledExams.of(tier)` (встроены в мод; внешние
  конфиги `<config>/gtnhextranerf/<tier>-exam.json` игнорируются — «the {} exam is part of the mod and no
  longer read from the configuration»). `verify()` (audit) проверяет регистрацию фабрик иRound-trip
  сериализацию бланка через `ExamProtocol`.
- **ExamDefinition**: id, tier, список `ExamQuestion`, массив эталонных ответов `correctOptions`,
  `requiredCorrect` (порог сдачи), `enabled`. LV-экзамен: 10 вопросов, ключ ответов вида строки
  `"BCADBCADCB"` (по букве на вопрос), варианты ≤15 (битовые маски ответов, `Integer.bitCount==1` — ровно один ответ).
- **ExamSyncHandler** (ModularUI SyncHandler, канал SYNC_ID; сообщения PAPER/RESULT/SUBMIT/PAY/ADMISSION):
  вся проверка — **только на сервере**; клиент получает «admission»-статус:
  - `ALREADY_CERTIFIED` — если `MachineProgression.isCertified(world, tier)`;
  - `UNAVAILABLE` — экзамен выключен/недоступен;
  - `INSUFFICIENT` — не списана пошлина `CertificationCost.take(player, tier)`;
  - иначе `ADMITTED` → создаётся `ExamAttempt(uuid, definition, awardCertificateRunnable)` и сервер шлёт бланк;
  - PAY (для MV+ без экзамена): сразу `MachineProgression.certify(world, tier)` → `CERTIFIED`.
- **ExamAttempt.submit(uuid, answers)** — серверная проверка: владелец UUID игрока, попытка одноразовая
  (`completed != null` → тот же результат), ответы валидны (диапазон 0..15, ровно один бит), затем
  `definition.score(answers)`; `score >= requiredCorrect` → PASSED и выполняется `awardCertificate.run()`
  (= выдача подписанного предмета сертификата), иначе FAILED. Статусы: READY/PASSED/FAILED/INVALID/INCOMPLETE/UNAVAILABLE.
- **CertificationCost** — таблица пошлин поSwitchMap тиров: LV — ingot Bronze x? + cableGt01 Tin;
  далее блоки металлов: Steel→Aluminium→StainlessSteel→Titanium→TungstenSteel→RhodiumPlatedPalladium(BW)→
  Iridium→Osmium→Neutronium→Infinity→TranscendentMetal→SpaceTime→MHDCSM. `take()` сканирует инвентарь,
  `consume(slots, material, amount)`, обновляет контейнер.

Типовой путь LV: игрок кликает ошибку `gtnhextranerf.progression.lv.error` («You are not OSHA certified to
handle electricity, click here to get your license») → открывается GUI экзамена «OSHA Electrical Safety Exam»
→ сдача → сервер выдаёт `lv_certificate` с epoch → ПКМ по предмету → `certify()` → машины разблокируются.

## 7. Отзыв сертификата за инциденты — CertificationIncidents

`CertificationIncidents.record(world, tier, incidentKey, dim, x/y/z)` (вызывается из ElectricalSafety/SteamSafety):
1. `MachineProgression.revoke(world, tier)` → бит снят, **epoch увеличен** (все старые предметы-сертификаты
   этого тира протухли);
2. лог warn `{tier} certification revoked after {incident} in dimension {dim} at {x},{y},{z}`;
3. чат всем: `gtnhextranerf.progression.<tier>.revoked`
   (например «Electrical certification revoked worldwide due to safety concerns: %s. Basic electric machines
   and energy/dynamo hatches are now paused.») + `gtnhextranerf.progression.incident.<key>`.

То есть аварийные ситуации (пожар кабеля, взрыв машины, ожог паром) могут «аннулировать лицензию» всего мира,
и чтобы её вернуть, нужно заново сдать экзамен/заплатить — новый сертификат будет иметь новый epoch.

## 8. Итоговая схема работы «сертификатов»

```
[Экзамен LV / Пошлина MV+] --PASSED--> issue(): ItemStack + NBT gtnhextranerf_certificate_epoch = currentEpoch(world)
        │
ПКМ по предмету: issuedEpoch == ProgressionData.certificateEpoch ?  ──нет──> "expired" (шанс 0, не расходуется)
        │да
MachineProgression.certify -> ProgressionData.unlock (бит в unlockedMask), markDirty -> save NBT gtnhextranerf_progression
        │
MixinProgressionTickGate/MixinMultiblockCertification на каждом тике: isLocked(mte)? -> setActive(false)
        │ (разлок мгновенно: все машины требуемого тира стартуют)
Инцидент (ElectricalSafety/SteamSafety) -> CertificationIncidents.record -> revoke: бит OFF + epoch++
        -> все выданные ранее предметы теперь «просрочены», машины по всему миру паузятся
```

Ключевые защиты от читов/злоупотреблений:
1. Подпись предмета epoch'ом мира + проверка при активации (нельзя забустить старый/скопированный сертификат).
2. Вся логика экзамена на сервере (UUID-владелец, одноразовость попытки, серверный скоринг, лимит вариантов).
3. Проверка «5 игровых часов» при сертификации экзаменационного тира → блок телеметрии для спидран-миров.
4. Audit-система (`AuditManager.verify`) при старте проверяет, что все mixin-хуки сертификации реально применились
   («Energy hatch certification hooks are missing», «Missing certificate: …»), т.е. мод деградирует
   с явной ошибкой, а не тихо оставляет мир без контроля.

## Исходники доказательств
- `decompiled/ProgressionCertificates.javap.txt`, `ProgressionCertificateItem` (в README-списке), `MachineProgression`,
  `ProgressionData`, `CertificationCost`, `EnergyHatchCertification`, `CertificationExams`, `ExamSyncHandler`, `ExamAttempt`
- Константы: `gtnhextranerf_progression`, `certifiedTiers`, `certificateEpochs`, `telemetryBlocked`,
  `gtnhextranerf_certificate_epoch`, `MINIMUM_WORLD_TICKS`(5h), `/extranerf-certificate <tier>`.
