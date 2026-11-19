#!/system/bin/sh
# PICO VR Multi-Window 2D 开机配置同步与临时 root 挂载
MODDIR=${0%/*}
CONF=/data/adb/pico_vr_multiwindow/config
[ -x "$MODDIR/control.sh" ] && sh "$MODDIR/control.sh" mount >/dev/null 2>&1

# 等待 sys.boot_completed
i=0
while [ $i -lt 60 ]; do
  [ "$(getprop sys.boot_completed 2>/dev/null)" = "1" ] && break
  i=$((i+1)); sleep 1
done

mkdir -p /data/adb/pico_vr_multiwindow
ENABLED=1
FORCE_RESIZE=1
OV_BRIDGE=1
OV_DENY=""
MAX_PANELS=6
if [ -f "$CONF" ]; then
  v=$(grep '^ENABLED=' "$CONF" 2>/dev/null | cut -d= -f2)
  [ -n "$v" ] && ENABLED=$v
  r=$(grep '^FORCE_RESIZE=' "$CONF" 2>/dev/null | cut -d= -f2)
  [ -n "$r" ] && FORCE_RESIZE=$r
  o=$(grep '^OV_BRIDGE=' "$CONF" 2>/dev/null | cut -d= -f2)
  [ -n "$o" ] && OV_BRIDGE=$o
  d=$(grep '^OV_BRIDGE_DENY=' "$CONF" 2>/dev/null | cut -d= -f2-)
  [ -n "$d" ] && OV_DENY=$d
  m=$(grep '^MAX_PANELS=' "$CONF" 2>/dev/null | cut -d= -f2)
  [ -n "$m" ] && MAX_PANELS=$m
fi

settings put global pico_vr_multiwindow "$ENABLED" 2>/dev/null
settings put global pico_vr_force_resize "$FORCE_RESIZE" 2>/dev/null
settings put global pico_vr_overlay_bridge "$OV_BRIDGE" 2>/dev/null
[ -n "$OV_DENY" ] && settings put global pico_vr_overlay_bridge_deny "$OV_DENY" 2>/dev/null
settings put system pvr.xrshell.overlay_panel_count "$MAX_PANELS" 2>/dev/null

# 等待 com.picoxr.xrshell 启动后拉起自愈与自动焦点守护
j=0
while [ $j -lt 30 ]; do
  XPID=$(pidof com.picoxr.xrshell 2>/dev/null)
  if [ -n "$XPID" ] && [ -x "$MODDIR/system/bin/mwctl" ]; then
    sh "$MODDIR/system/bin/mwctl" repatch >/dev/null 2>&1 && break
  fi
  j=$((j+1)); sleep 1
done
