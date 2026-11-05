# Recovery as a disposable kernel test bed

PD2048 的 `recovery.img` 和 `boot.img` 里是**同一个内核**，所以 recovery 分区可以
当"一次性内核试验台"：换掉 recovery 的内核，启动一次，验证完就让它自动还原。

```
boot.img      kernel 14,168,565 B  md5 2f17f1623ddd2462ac1298d39e3520ba
recovery.img  kernel 14,168,565 B  md5 2f17f1623ddd2462ac1298d39e3520ba
```

## 为什么可行

| 条件 | 事实 |
|---|---|
| 内核一致 | 两个镜像 header 里 `kernel_size` 相同，内核段逐字节相同（md5 见上） |
| 能写 | recovery 在 LBA 0x8（32 KiB），96 MiB，**在 UFS WP 区外**（WP 从扇区 0x32800 = 808 MiB 开始）；Android root 下 `dd` 可持久写入 |
| 坏了不心疼 | 每次正常启动时 preloader/LK 把 recovery 还原成原厂；写坏的 recovery 只影响那一次启动 |
| 不用过门禁 | 走 Android 侧 `dd`，不经过 LK fastboot 的 `fb_get_verify_unlock_state` 检查 |

## 步骤

1. 拼镜像（stock recovery + 自编内核，ramdisk/DTBO 原样保留）：

   ```bash
   python -I tools/splice_boot.py \
       --stock recovery.img \
       --kernel Image.gz \
       --out recovery_pd2048_test.img
   ```

   建议用带 adb root 的 recovery ramdisk（`ro.debuggable=1`、`ro.adb.secure=0`、
   `service.adb.root=1`），否则 recovery 里 adb 可能不是 root。

2. 写分区（手机已临时 root）：

   ```bash
   adb push recovery_pd2048_test.img /data/local/tmp/
   adb shell dd if=/data/local/tmp/recovery_pd2048_test.img \
                 of=/dev/block/by-name/recovery bs=1M
   adb shell md5sum /dev/block/by-name/recovery   # 与本地 md5 对照
   ```

3. 写 BCB 并重启：

   ```bash
   adb shell 'dd if=/dev/zero of=/dev/block/by-name/misc bs=512 count=1'
   adb shell "printf boot-recovery | dd of=/dev/block/by-name/misc bs=1 count=13 conv=notrunc"
   adb reboot
   ```

4. 验证：

   ```bash
   adb shell cat /proc/version        # 期望 4.14.186+ (pd2048@gha)
   adb shell dmesg | grep -iE 'probe.*(fail|error)|s6e3fc3|goodix|tfa9874'
   ```

   `dmesg` 里 probe 失败的设备就是下一步要补的 DTS/驱动清单。

5. 退出：`adb reboot` 回正常系统即可，recovery 会在这次启动时恢复原厂。

自动化脚本：`tools/test_kernel_via_recovery.py`（push → 写 → 回读校验 → BCB → 重启 →
读 `/proc/version`；支持 `--check` 只看不写）。

## 局限

* 面板驱动没移植时屏幕不亮，只能靠 adb；这是预期行为，不是启动失败。
* recovery 模式不能替代日常 boot。要日常使用自编内核，仍然要解决 LK 的
  `verify_unlock_state` 门禁（见 `STATUS.md`）。
* 如果内核在 recovery 里挂死：长按电源 15–20 s 复位，下一次正常启动会自动还原
  recovery，不会变砖。
