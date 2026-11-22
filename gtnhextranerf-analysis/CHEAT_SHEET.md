# GTNH Extra Nerf — как получить ВСЕ сертификаты в тестовом мире (креатив)

Мод НЕ содержит команды "/give all". Проверено по байткоду: единственная команда мода —
`/extranerf-certificate <tier>` (уровень доступа 0), и она только ОТКРЫВАЕТ GUI сертификата,
не выдавая его. Поэтому есть 3 рабочих способа.

## Ключевые факты из кода (для понимания)

1. Состояние тира хранится глобально в мире: `WorldSavedData` с именем
   `gtnhextranerf_progression`, загружается из **level.dat** (через MapStoragedim0).
   Поля NBT:
   - `certifiedTiers` — compounds с флагами boolean по id тиров
     (`lv`,`steam`,`mv`,`hv`,`ev`,`iv`,`luv`,`zpm`,`uv`,`uhv`,`uev`,`uiv`,`umv`,`uxv`,`max`)
   - `certificateEpochs` — long по каждому тиру (счётчик «переизданий», растёт при revoke)
   - `telemetryBlocked` — boolean
2. Предметы-сертификаты регистрируются как обычные предметы:
   `gtnhextranerf:<tier>_certificate` (например `gtnhextranerf:mv_certificate`).
   При активации (ПКМ) предмет сверяет эпоху из своего NBT-ключа
   `gtnhextranerf_certificate_epoch` с текущей эпохой мира. Если ключа нет — считается epoch=0,
   что совпадает с новым миром → предмет работает.
3. Машины проверяют не предмет, а битовую маску `unlockedMask` в ProgressionData
   (MixinProgressionTickGate / MixinMultiblockCertification). Т.е. важен именно saved-data.

## Способ 1 (рекомендуемый): NBT-правка level.dat — мгновенно все тиры

1. Полностью остановите сервер/закройте мир.
2. Откройте `<мир>/level.dat` любым NBT-редактором (MCEdit Universal MCA Format /
   NBTExplorer / `nbtlib` в python). Внутри `Data` создайте/исправьте compound
   `gtnhextranerf_progression` (если файла `gtnhextranerf_progression.dat` ещё нет, он будет
   создан модам при сохранении — правим прямо в level.dat секцию SavedData):

```
gtnhextranerf_progression {
    certifiedTiers { steam=1b, lv=1b, mv=1b, hv=1b, ev=1b, iv=1b, luv=1b, zpm=1b,
                     uv=1b, uhv=1b, uev=1b, uiv=1b, umv=1b, uxv=1b, max=1b }
    certificateEpochs { steam=0L, lv=0L, mv=0L, hv=0L, ev=0L, iv=0L, luv=0L, zpm=0L,
                        uv=0L, uhv=0L, uev=0L, uiv=0L, umv=0L, uxv=0L, max=0L }
}
```

3. Сохраните, запустите мир — все машины всех тиров разблокированы (readFromNBT собирает
   unlockedMask из флагов certifiedTiers). Эпохи = 0 → выданные вручную сертификаты тоже валидны.

Быстро через python (нужен `pip install anvil-parser` или mca_nbt):

```python
import nbt.nbt, nbt.region
from nbt.tags import *
# level.dat — gzip-сжатый NBT без сжатия секций
with open('level.dat','rb') as f: raw=f.read()
import gzip, io
from nbtlib import File
nbt = File.load('level.dat')
p = nbt['Data'].setdefault('gtnhextranerf_progression', {})
tiers=['steam','lv','mv','hv','ev','iv','luv','zpm','uv','uhv','uev','uiv','umv','uxv','max']
p['certifiedTiers'] = {t: True for t in tiers}
p['certificateEpochs'] = {t: 0 for t in tiers}
nbt.save('level.dat')
```

## Способ 2: креатив-инвентарь + ПКМ по очереди

Сертификаты добавлены во вкладку «Building Blocks» (`CreativeTabs.f_Blocks`):
`gtnhextranerf:lv_certificate`, `..._steam_certificate`, `..._mv_certificate`, `..._hv_certificate`,
`..._ev_certificate`, `..._iv_certificate`, `..._luv_certificate`, `..._zpm_certificate`,
`..._uv_certificate`, `..._uhv_certificate`, `..._uev_certificate`, `..._uiv_certificate`,
`..._umv_certificate`, `..._uxv_certificate`, `..._max_certificate`.

Держа в руке — нажать ПКМ → `MachineProgression.certify(world, tier)` ставит бит тира
(и обязательные предыдущие тиры через REQUIRED_MASK). В новом мире epochs=0, поэтому
предмет из креатива без NBT проходит проверку эпохи.

Через give-команду (нужен OP/gamemode creative, уровень доступа команды 0 не требуется для vanilla /give):

```
/give @p gtnhextranerf:max_certificate 15
```
Затем держать каждый в руке и жать ПКМ. Порядок не важен — REQUIRED_MASK сам дотянет младшие тиры.

⚠ Нюанс: если в мире уже был инцидент (revoke) и epoch тира > 0, предмет из креатива
(epoch=0) покажет «просрочен». Тогда используйте способ 1 или выдайте сертификат со
свежей эпохой командой из лога сервера либо просто откатите epoch в level.dat на 0.

## Способ 3: консоль/скрипт на стороне сервера (для автоматизации теста)

Через CraftTweaker/GroovyConsole или любой доступ к классам мода:

```java
World w = MinecraftServer.getServer().worldServers[0];
for (ProgressionTier t : ProgressionTier.values())
    MachineProgression.certify(w, t);   // ставит бит + save flag
// либо напрямую:
ProgressionData d = w.mapStorage.loadData(ProgressionData.class, "gtnhextranerf_progression");
d.unlock(t); d.markDirty();
```

## Бонус: обход экзамена LV

LV-сертификат в нормальном режиме выдаётся только через экзамен
«OSHA Electrical Safety Exam» (10 вопросов). Для теста просто поставьте флаг
`lv=1b` в `certifiedTiers` (способ 1) — экзамен пропускается, т.к. проверка идёт только
по unlockedMask. Учтите анти-спидран правило: LV до истечения 5 игровых часов мира
навсегда ставит `telemetryBlocked=1` — на геймплей не влияет, только телеметрию.

## Как проверить, что всё применилось

В консоли сервера: `/extranerf-certificate mv` откроет GUI статуса; либо grep лога на строки
audit-системы ("Missing certificate:") — при полном unlockedMask их быть не должно.
