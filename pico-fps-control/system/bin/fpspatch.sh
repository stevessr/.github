#!/system/bin/sh
# fpspatch.sh <allow60|force90|restore>
# 运行时内存补丁（不修改分区，重启失效）
M=/data/adb/modules/pico_fps_control/system/bin
LIB=libpxrhmdservice.so
P=$(pidof pxrhmdservice)
[ -z "$P" ] && exit 1

# BaseDevice::checkRefreshRateValid  @ file offset 0x399e8  ->  mov w0,#1 ; ret
# HawkDev::setRefreshRate request    @ file offset 0x3a198  ->  mov w20,#90 (or original)
WL=399e8
F90=3a198

case "$1" in
  allow60)
    "$M/patch8lib" "$P" "$LIB" "$WL" 20 00 80 52 c0 03 5f d6 >/dev/null 2>&1
    ;;
  force90)
    "$M/patch8lib" "$P" "$LIB" "$WL" 20 00 80 52 c0 03 5f d6 >/dev/null 2>&1
    "$M/patch8lib" "$P" "$LIB" "$F90" 54 0b 80 52 a8 03 1d f8 >/dev/null 2>&1
    ;;
  restore)
    "$M/patch8lib" "$P" "$LIB" "$F90" f4 03 01 2a a8 03 1d f8 >/dev/null 2>&1
    "$M/patch8lib" "$P" "$LIB" "$WL" 5f 24 03 d5 48 0b 80 52 >/dev/null 2>&1
    ;;
  verify)
    "$M/patch8lib" "$P" "$LIB" "$WL" 20 00 80 52 c0 03 5f d6 2>/dev/null | head -1
    "$M/patch8lib" "$P" "$LIB" "$F90" 54 0b 80 52 a8 03 1d f8 2>/dev/null | head -1
    ;;
esac
exit 0
