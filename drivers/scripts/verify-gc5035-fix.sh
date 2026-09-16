#!/usr/bin/env bash
# GC5035 iovdd/DOVDD 修复验证 (重启后运行)
set -u
echo "=========== 1. 模块 srcversion (应含修复) ==========="
for m in intel_skl_int3472_discrete gc5035 ov5678 ipu-bridge; do
  printf "%-30s " "$m"
  modinfo "$m" 2>/dev/null | grep -m1 srcversion || echo "(not loaded)"
done
echo
echo "=========== 2. int3472 电源轨 (dmesg) ==========="
sudo dmesg | grep -iE "int3472|ignoring|regulator|iovdd|dovdd" | tail -25
echo
echo "=========== 3. gc5035 probe 结果 ==========="
sudo dmesg | grep -iE "gc5035|chip_id|Sensor ID|5035|-121|EREMOTEIO" | tail -30
echo
echo "=========== 4. 是否注册了 v4l2 sensor ==========="
if dmesg | grep -qiE "gc5035.*Sensor ID.*0x5035|gc5035.*detected"; then
  echo "*** GC5035 probe SUCCESS ***"
else
  if dmesg | grep -qiE "gc5035.*-121"; then
    echo "!!! GC5035 -121 仍然存在 !!!"
  else
    echo "(无明确判定，请人工检查上面日志)"
  fi
fi
echo
echo "=========== 5. gpio consumer ==========="
sudo gpioinfo -c gpiochip0 2>/dev/null | grep -E "line *(96|97|100|101):"
echo
echo "=========== 6. i2c-0 GCTI5035 绑定 ==========="
ls -l /sys/bus/i2c/devices/i2c-GCTI5035:00/driver 2>/dev/null || echo "(未绑定 driver)"
