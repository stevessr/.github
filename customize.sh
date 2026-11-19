#!/system/bin/sh
SKIPUNZIP=0

ui_print "****************************************"
ui_print "  PICO 2D Window Scale & Distance v1.0.0"
ui_print "  2D 窗口更大缩放 & 更远推送 (临时 Root)"
ui_print "****************************************"

set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/system/bin/winctl" 0 2000 0755
set_perm "$MODPATH/system/bin/winscale_patch" 0 2000 0755
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755

mkdir -p /data/adb/pico_window_scale_dist
if [ ! -f /data/adb/pico_window_scale_dist/config.env ]; then
  cat > /data/adb/pico_window_scale_dist/config.env <<'EOF'
ENABLED=1
MAX_DIST=60
MAX_W=6400
MAX_H=3600
EOF
fi

if sh "$MODPATH/system/bin/winctl" apply >/dev/null 2>&1; then
  ui_print "- 已即时注入运行中的 XRShell，无需重启即可生效！"
else
  ui_print "- 安装完成，将在 XRShell 启动后自动应用。"
fi
