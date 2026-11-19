#!/system/bin/sh
# whitelist_patch.sh - 放开 pxrhmdservice 的帧率白名单（仅 RAM，重启失效）
BIN=/data/adb/modules/pico_fps_control/system/bin
P=$(pidof pxrhmdservice)
[ -z "$P" ] && exit 1
BASE=$(grep 'libpxrhmdservice.so' /proc/$P/maps 2>/dev/null | grep 'r-xp' | head -1 | cut -d- -f1)
[ -z "$BASE" ] && exit 1
# 已打过则跳过（检查首字节是否为 mov w0,#1）
CUR=$($BIN/patchval "$P" "$BASE" 399e8 24000 2>/dev/null | grep 'current:' | awk '{print $2}')
[ "$CUR" = "20" ] && exit 0
$BIN/patchval "$P" "$BASE" 399e8 24000 >/dev/null 2>&1
