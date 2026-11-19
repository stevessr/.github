#!/system/bin/sh
# KSU 模块开机脚本 (post-fs-data 后执行)
MODDIR=${0%/*}
[ -z "$MODDIR" ] && MODDIR=/data/adb/modules/pico_fps_control
BIN=$MODDIR/system/bin
CONF=/data/adb/pico_fps/config
LOG=/data/adb/pico_fps/fpsd.log
mkdir -p /data/adb/pico_fps
chmod 755 "$BIN"/* 2>/dev/null

# 等待 root（临时 DF 越狱后 su 才可用），最多 5 分钟
i=0
while [ $i -lt 150 ]; do
  su -c true 2>/dev/null && break
  i=$((i+1)); sleep 2
done
echo "[$(date)] service.sh: root ready after ${i} tries" >> "$LOG"

# 应用已保存的固定帧率
if [ -f "$CONF" ]; then
  MODE=$(grep '^MODE=' "$CONF" | cut -d= -f2)
  FPS=$(grep '^FPS=' "$CONF" | cut -d= -f2)
  [ "$MODE" = "fixed" ] && "$BIN/fpsctl" set "${FPS:-72}" >> "$LOG" 2>&1
fi

# 启动守护
"$BIN/fpsd-start" >> "$LOG" 2>&1
echo "[$(date)] service.sh done" >> "$LOG"
