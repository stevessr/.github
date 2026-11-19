#!/system/bin/sh
MODDIR=${0%/*}
if [ -x "$MODDIR/system/bin/winctl" ]; then
  sh "$MODDIR/system/bin/winctl" reset >/dev/null 2>&1
fi
rm -rf /data/adb/pico_window_scale_dist
