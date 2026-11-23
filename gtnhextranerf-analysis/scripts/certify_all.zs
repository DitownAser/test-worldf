// ============================================================
// GTNH Extra Nerf (gtnhextranerf) — ВЫДАЧА ВСЕХ СЕРТИФИКАТОВ
// Файл: scripts/certify_all.zs   (CraftTweaker 3, MC 1.7.10)
// Для GTNH 2.9.x / 2.10.x (New Horizons Composite)
// ------------------------------------------------------------
// Как это работает:
//   Мод хранит прогресс в WorldSavedData "gtnhextranerf_progression"
//   и проверяет машины по битовой маске unlockedMask. Поэтому мы
//   просто вызываем public static метод мода:
//     pl.kuba6000.gtnhextranerf.progression.MachineProgression.certify(World, ProgressionTier)
//   для каждого тира. certify() сам дотягивает обязательные
//   предыдущие тиры через REQUIRED_MASK.
//
// КУДА ПОЛОЖИТЬ:
//   .minecraft/saves/<имя мира>/scripts/certify_all.zs
//   (в одиночной игре скрипты из saves/<мир>/scripts выполняются при загрузке мира;
//    на сервере — в корне сервера: <server>/scripts/... или config/crafttweaker/)
//
// ВАЖНО (GTNH 2.9.0):
//   В сборках GTNH скрипты выполняются с SAFE LOAD MODE — обычный .zs
//   может не увидеть классы модов. Поэтому используем //%GTMODSCRIPT ... %CT
//   прямую Java-вставку (поддерживается CraftTweaker 3 в составе GTNH).
//   Если ваш запуск ругается на GTMODSCRIPT — удалите строки //%GTMODSCRIPT и %CT,
//   оставьте тело между ними как обычный .zs (иногда достаточно просто .zs).
// ============================================================

//%GTMODSCRIPT
import java.util.List;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.World;
import pl.kuba6000.gtnhextranerf.progression.MachineProgression;
import pl.kuba6000.gtnhextranerf.progression.ProgressionTier;

// Получаем overworld (dim 0) напрямую через MinecraftServer —
// самый надёжный способ в CT3/GTNH (не зависит от привязки <world:...>).
server = MinecraftServer.getServer();
worlds: List = server.allWorlds();
overworld = null;
for (w in worlds) {
    if (w != null && w.provider.dimensionId == 0) {
        overworld = w;
    }
}
if (overworld == null) {
    print("[certify_all] ОШИБКА: overworld не найден (мир ещё не загружен?).");
} else {
    // certify() сам подтягивает обязательные младшие тиры (REQUIRED_MASK),
    // но вызываем все по значениям enum — порядок не важен.
    for (tier in ProgressionTier.values()) {
        ok = MachineProgression.certify(overworld, tier);
        print("[certify_all] " + tier.id() + " -> " + ok);
    }
    print("[certify_all] Готово: все сертификаты GTNH Extra Nerf активированы.");
}
//%CT
