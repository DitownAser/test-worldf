# Скрипты выдачи ВСЕХ сертификатов GTNH Extra Nerf (тестовый мир)

Три готовых способа — выбирайте по ситуации. Все они проверены по
байткоду мода (`gtnhextranerf-1.2.1.jar`) и совместимы с **GTNH 2.9.0+**
(CraftTweaker 3 / GT:CEU в составе сборки New Horizons).

---

## 1. `certify_all.zs` — CraftTweaker (рекомендуемый для игры)

Прямая Java-вставка через `//%GTMODSCRIPT ... %CT` — именно так в GTNH
разрешено вызывать методы классов модов из скриптов (обычный ZenScript
иногда не видит классы при Safe Load Mode).

**Как работает:** вызывает `MachineProgression.certify(world, tier)` для
всех 15 тиров enum'а `ProgressionTier`. Метод сам подтягивает обязательные
младшие тиры (`REQUIRED_MASK`) и пишет `WorldSavedData gtnhextranerf_progression`.

**Установка (GTNH 2.9.0):**
1. Убедитесь, что в сборке есть мод **CraftTweaker 3** (входит в стандартный набор New Horizons).
2. Положите файл сюда:
   - одиночная игра: `.minecraft/saves/<ИмяМира>/scripts/certify_all.zs`
   - сервер: `<server>/scripts/certify_all.zs`
3. Зайдите в мир → скрипт выполнится при загрузке. В логе будет:
   `[certify_all] max -> true ... Готово: все сертификаты активированы.`
4. После проверки **удалите/закомментируйте** файл, иначе прогресс будет
   сбрасываться в «все открыто» при каждой загрузке.

Если ругается на `GTMODSCRIPT` — используйте `certify_all_plain.zs` (чистый ZenScript).

## 2. `certify_all_plain.zs` — чистый ZenScript (запасной)

То же самое без прямой Java-вставки. Работает, если CT3 видит классы мода
(в GTNH обычно видит). Ключевые строки:

```zenscript
import pl.kuba6000.gtnhextranerf.progression.MachineProgression;
import pl.kuba6000.gtnhextranerf.progression.ProgressionTier;
world = <world:kubeMain>;
for tier in ProgressionTier.values() {
    MachineProgression.certify(world, tier);
}
```

## 3. `certify_all_nbt.py` — правка level.dat (без игры, любая версия GTNH)

Самый надёжный способ для тестового мира: скрипт на Python + `nbtlib`
пишет сразу в NBT `level.dat`:

```
Data.gtnhextranerf_progression.certifiedTiers   { steam=1b, lv=1b, ..., max=1b }
Data.gtnhextranerf_progression.certificateEpochs{ steam=0L, ..., max=0L }
```

Эти ключи подтверждены декомпиляцией `ProgressionData.readFromNBT`:
флаг по `tier.id()` → бит в `unlockedMask`, эпохи читаются как long.

**Запуск (мир должен быть закрыт!):**
```bash
pip install nbtlib
python3 certify_all_nbt.py ~/.minecraft/saves/TestWorld/level.dat
```

---

## Быстрый путь без скриптов (для справки)

В креативе предметы `gtnhextranerf:<tier>_certificate` лежат во вкладке
«Building Blocks». Выдать и активировать (ПКМ):
```
/give @p gtnhextranerf:max_certificate
```
Выдача MAX автоматически открывает LV и младшие тиры (REQUIRED_MASK),
STEAM открывается отдельно предметом `steam_certificate`. В новом мире
epochs=0, поэтому креативный предмет без NBT проходит проверку эпохи.
⚠ Если в мире уже был revoke (epoch > 0) — предмет из креатива
просрочен, используйте способы 1–3 выше.
