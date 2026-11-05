# PD2048 driver gaps (bomb cezanne-r-oss base)

From `_research/driver_inventory.csv` (561 unique compatibles in the stock PD2048
DTB, 294 present in the bomb tree, 267 missing). Most of the 267 MTK entries are
naming/version drift between Android 11 (bomb) and Android 13 (PD2048) and are
expected to be handled by merging subsystems, not one-by-one ports.

## Hard gaps — vivo private (13)

| compatible | role |
|---|---|
| `vivo,battery` | battery gauge glue |
| `vivo,battery_id` | battery id detect |
| `vivo,charge` | charge policy |
| `vivo,charger-monitor-v2` | charger monitor |
| `vivo,fuelsummary` | fuel summary |
| `vivo,meter` | coulomb meter |
| `vivo,mobile_event` | event bridge |
| `vivo,power_supply_lite` | power supply core |
| `vivo,touch-panel-module` | touch module |
| `vivo,ts-spi` | touch SPI transport |
| `vivo,typec-switch` | type-c switch |
| `vivo,vendor_board_info` | board info |
| `vivo,vivo-audio-ktv` | audio ktv |

## Panel (3)

| compatible | notes |
|---|---|
| `pd2048samsung,s6e3fc3,cmd90hz` | Samsung OLED 1080x2400, 90 Hz |
| `pd2048samsung,s6e3fc3,cmd60hz` | same panel, 60 Hz |
| `pd2048samsung2,s6e3fc3,cmd90hz` | second source |

## Peripherals (6)

| compatible | role |
|---|---|
| `goodix,gt9885-spi` | touch controller |
| `tfa,tfa9874` | speaker amp |
| `ti,bq25601d` | charger |
| `ti,bq25890h` | charger |
| `st,st32l011-mcu` | mcu |
| `maxin,max20328` | type-c switch |

## Where the code comes from

* vivo's public kernel drops (e.g. `android_13.0_kernel_MT6833`, 4.19.191) ship
  the vivo touch framework (`drivers/input/touchscreen/drivers/vts_core.c`,
  `vts_spi_drv.c`) and the `include/linux/power/vivo/*` headers, but not the
  PD2048 charge stack or the s6e3fc3 panel driver.
* The stock PD2048 kernel has all of them built in (`/vendor/lib/modules` only
  contains wifi/bt/gps/met), so the panel init sequence and the vivo charge
  drivers have to be recovered from the stock `Image` (kallsyms + disassembly)
  or backported from another vivo drop.

## Build-verified gaps (stock config on the bomb tree)

Building `pd2048_defconfig` (the stock `/proc/config.gz`) on the bomb tree exposes
the real, compiler-confirmed gaps — much more precise than the compatible-string
inventory:

1. `drivers/gpu/drm/drm_gem.c` and `drivers/input/touchscreen/GT9886` need
   `-I drivers/gpu/drm/mediatek/`, which the Makefiles only add under
   `CONFIG_DRM_MEDIATEK_BOMB`. The stock config only sets vivo's
   `CONFIG_DRM_MEDIATEK`. **Fix: add `CONFIG_DRM_MEDIATEK_BOMB=y`** (done).
2. `CONFIG_EXTRA_FIRMWARE` listed `tfa98xx_PD2048.cnt`, which is not in the tree.
   **Fix: keep only `valhall-1691526.wa`** (done); the amp firmware can be loaded
   from `/vendor/firmware` at runtime.
3. `mtk_battery_core.c` uses `of_find_device_by_node`, `iio_channel_get`,
   `iio_read_channel_processed` — the stock config enables the battery driver but
   the headers were missing. **Fixed**: `patches/0002-battery-iio-includes.patch`.
4. `drivers/misc/mediatek/base/power/swpm_v1/mtk_swpm.c` needs
   `mtk_gpu_power_sspm_ipi.h` (exists in the stock tree only). **Fixed** by 6.
5. `mali-r32p1/drivers/gpu/arm/midgard/Makefile` and
   `imgsensor/.../gc02m1bv1_mipi_mono/Makefile` are referenced by the stock config
   but absent from the bomb tree (different Mali/sensor layout).
6. `CONFIG_MTK_GPU_VERSION="mali valhall r32p1"` (CI run #28) has no matching
   `mali-r32p1` directory in the bomb tree (only `mali-r21p0` / `mali-r25p0`), so
   `mtk_swpm.c` cannot find `mtk_gpu_power_sspm_ipi.h`. **Fixed**: keep `r25p0`
   (same G57 IP, older DDK label).
7. **New (CI run #30):** the stock config keeps `CONFIG_MTK_CHARGER` off (vivo
   ships its own charge stack), but `CONFIG_MTK_GAUGE_VERSION=30` still builds the
   MTK battery driver, which references `charger_manager_*`,
   `charger_device_*` and `BATTERY_SetUSBState`. **Fixed**: `CONFIG_MTK_CHARGER=y`
   (generic MTK charger provides them).
8. **New (CI run #28):** none of the seven PD2048 image sensors exist in the bomb
   tree, and the imgsensor Makefile turns every missing entry into a
   `../common/v1_1/<name>/` build target. **Fixed for bring-up**:
   `CONFIG_CUSTOM_KERNEL_IMGSENSOR=""` (camera core still builds, no sensors).

Conclusion: `pd2048_defconfig` **builds as of CI run #31** (commit 8033f4a).
The remaining work is runtime bring-up, not compilation: the stock config still
enables many PD2048-only drivers that will fail to probe (no matching hardware
description or no driver in the tree), which is exactly what the recovery test
bed is for.

## Bring-up order

1. boot with stock DTB, no display, adb only — validates UFS/USB/CPU
2. touch (`gt9885` + `vts`), battery/charger stubs
3. panel `s6e3fc3` init sequence
4. audio amp, type-c switch, fingerprint
