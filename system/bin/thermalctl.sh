#!/system/bin/sh
# thermalctl.sh - PICO 4 Ultra thermal-engine-v2 温控覆盖管理
CONF_DIR=/data/adb/pico_fps
OVR_CONF=$CONF_DIR/thermal-override.conf
TARGET=/vendor/etc/thermal-engine-sparrow.conf

write_override_conf() {
  mkdir -p "$CONF_DIR"
  cat > "$OVR_CONF" <<'EOF'
# PICO FPS Control - 保留电池安全监控，移除原厂风扇降速策略
[BCL_MONITOR]
algo_type monitor
sampling 10000
sensor socd
thresholds	-1	0	80	95
thresholds_clr	-1	0	79	94
actions		ibat	ibat	ibat	ibat
action_info	0	0	1	2
EOF
  chmod 644 "$OVR_CONF"
  chcon u:object_r:vendor_configs_file:s0 "$OVR_CONF" 2>/dev/null
}

is_mounted() {
  grep -q " $TARGET " /proc/mounts 2>/dev/null
}

restart_thermal() {
  stop thermal-engine >/dev/null 2>&1
  sleep 0.3
  start thermal-engine >/dev/null 2>&1
}

case "$1" in
  override)
    write_override_conf
    if ! is_mounted; then
      mount --bind "$OVR_CONF" "$TARGET" 2>/dev/null
      restart_thermal
    fi
    echo "thermal_override=1"
    ;;
  restore)
    if is_mounted; then
      umount "$TARGET" 2>/dev/null
      restart_thermal
    fi
    echo "thermal_override=0"
    ;;
  status)
    if is_mounted; then echo "thermal_override=1"; else echo "thermal_override=0"; fi
    echo "thermal_svc=$(getprop init.svc.thermal-engine 2>/dev/null)"
    ;;
  *)
    echo "usage: thermalctl.sh override|restore|status"
    ;;
esac
