// ============================================================
// GTNH Extra Nerf — выдача ВСЕХ сертификатов (запасной вариант)
// Чистый ZenScript (без //%GTMODSCRIPT), если прямая Java-вставка
// не прошла в вашей сборке GTNH 2.9.x.
//
// КУДА ПОЛОЖИТЬ: <мир>/scripts/certify_all_plain.zs  (одиночка)
//                или <server>/scripts/              (сервер)
//
// Требует, чтобы классы gtnhextranerf были видны CraftTweaker
// (обычно видны — CT3 в GTNH рефлексит классы модов по умолчанию).
// ============================================================

import pl.kuba6000.gtnhextranerf.progression.MachineProgression;
import pl.kuba6000.gtnhextranerf.progression.ProgressionTier;

world = <world:kubeMain>;   // overworld dim 0

for tier in ProgressionTier.values() {
    MachineProgression.certify(world, tier);
}

print("[certify_all_plain] Все сертификаты GTNH Extra Nerf активированы.");
