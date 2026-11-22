# Разбор мода GTNH Extra Nerf (gtnhextranerf-1.2.1.jar)

Мод для **GTNewHorizons** (GregTech New Horizons, Minecraft 1.7.10, Forge + Mixin), автор `pl.kuba6000`.
Название — «Extra Nerf», т.е. дополнительные «нерфы» (ослабления/ограничения) механик GTNH: прогрессия через
**сертификаты**, экзамены, лимиты лута, нерф рецептов, безопасность электричества/пара и т.д.

## Структура JAR (465 записей)

```
META-INF/MANIFEST.MF
mixins.gtnhextranerf.json            — конфиг Mixin (early / late разделены)
mixins.gtnhextranerf.early.json
mixins.gtnhextranerf.late.json
mcmod.info                            — метаданные мода
assets/gtnhextranerf/                 —.lang строки, текстуры (certificates, gui, machines), гид (guidenh/*.md)
pl/kuba6000/gtnhextranerf/
├── GTNHExtraNerf.class               — @Mod точка входа
├── CommonProxy / ClientProxy         — загрузка (preInit/init/postInit)
├── Config.class                      — конфиг мода
├── audit/        — AuditManager/AuditScope/AuditHandle: система самопроверок («аудит») после загрузки:
│                   каждый подсистема регистрирует verify(), которая проверяет, что её миксины/хуки на месте
├── progression/  — ★ СИСТЕМА СЕРТИФИКАТОВ (см. CERTIFICATES_SYSTEM.md)
│   ├── exam/     — экзаменационная подсистема (вопросы, лист ответов, протокол пакета)
│   ├── quest/    — интеграция с BetterQuesting
│   ├── ProgressionTier, ProgressionData, MachineProgression,
│   │   ProgressionCertificates, ProgressionCertificateItem, CertificationCost,
│   │   EnergyHatchCertification, CertificationIncidents, TelemetryEligibility, SteamSafety, ElectricalSafety
├── mixins/late/  — ~60 mixin'ов, из них сертификационные:
│   │   MixinMultiblockCertification, MixinProgressionTickGate, MixinProgressionMachineStatus,
│   │   MixinEnergyPorts, MixinWirelessHatchCertification, MixinWirelessCoverCertification, MixinSteamMultiBlock ...
├── loader/       — загрузчики предметов/лутов/рецептов (ComponentLoader, LootLoader, RecipeLoader)
├── loot/         — система лимитов лута (GlobalLootLimits, BagVariant...)
├── machines/ironbath/ — кастомная машина «Iron Bath»
├── components/, fabrication/, items/, materials/, recipes/, teams/, telemetry/, update/, warp/, net/
```

## Как проводился разбор

1. JAR распакован в `jar_contents/` (zipfile Python).
2. Байткод декомпилирован через `javap -p -c` → тексты в `decompiled/*.javap.txt`.
3. Строковые константы (имена NBT-тегов, ключи lang, ID) извлечены напрямую из constant pool классов.

Основные артефакты:
- `CERTIFICATES_SYSTEM.md` — полный разбор системы сертификатов (главный вопрос пользователя)
- `decompiled/` — javap-дампы ключевых классов
