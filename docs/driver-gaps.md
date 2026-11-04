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

## Bring-up order

1. boot with stock DTB, no display, adb only — validates UFS/USB/CPU
2. touch (`gt9885` + `vts`), battery/charger stubs
3. panel `s6e3fc3` init sequence
4. audio amp, type-c switch, fingerprint
