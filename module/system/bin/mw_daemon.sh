#!/system/bin/sh
# mw_daemon.sh - PICO VR Multi-Window 焦点自动切换 & XRShell 补丁自愈守护
export PATH=/system/bin:/vendor/bin:/data/adb/ksu/bin:$PATH
MODDIR=/data/adb/modules/pico_vr_multiwindow
PATCHER=$MODDIR/system/bin/xrshell_dist_patch
CONF=/data/adb/pico_vr_multiwindow/config
PIDF=/data/adb/pico_vr_multiwindow/mw_daemon.pid

mkdir -p /data/adb/pico_vr_multiwindow
echo $$ > "$PIDF"

# 观影/非游戏类 VR 应用（自动模式下默认允许直接操控 2D 窗口）
MEDIA_PKGS="com.pvr.vrshell com.google.android.apps.youtube.vr.pico com.google.android.apps.youtube.vr com.picovr.wing.videoplayer com.picovr.gallery_local com.pico.gallery"

last_pid=""
last_foc=""

while true; do
  FMODE=$(grep '^FOCUS_MODE=' "$CONF" 2>/dev/null | cut -d= -f2)
  [ -z "$FMODE" ] && FMODE="menu"
  DPATCH=$(grep '^DIST_PATCH=' "$CONF" 2>/dev/null | cut -d= -f2)
  [ -z "$DPATCH" ] && DPATCH="1"

  XPID=$(pidof com.picoxr.xrshell 2>/dev/null)
  if [ -n "$XPID" ] && [ -x "$PATCHER" ]; then
    # XRShell 重启后重新应用远近补丁
    if [ "$XPID" != "$last_pid" ]; then
      last_pid="$XPID"
      last_foc=""
      if [ "$DPATCH" = "1" ]; then
        "$PATCHER" "$XPID" dist_patch >/dev/null 2>&1
      else
        "$PATCHER" "$XPID" dist_restore >/dev/null 2>&1
      fi
    fi

    WANT_FOC="focus_patch"
    if [ "$FMODE" = "always2d" ]; then
      WANT_FOC="focus_restore"
    elif [ "$FMODE" = "hover" ]; then
      WANT_FOC="focus_hover"
    elif [ "$FMODE" = "auto" ]; then
      TOP=$(settings get global pvr.app.data.top_app_on_default_display 2>/dev/null | cut -d/ -f1)
      IS_MEDIA=0
      for p in $MEDIA_PKGS; do
        [ "$TOP" = "$p" ] && IS_MEDIA=1 && break
      done
      [ "$IS_MEDIA" = "1" ] && WANT_FOC="focus_restore" || WANT_FOC="focus_patch"
    else
      WANT_FOC="focus_patch"
    fi

    if [ "$WANT_FOC" != "$last_foc" ]; then
      if [ "$WANT_FOC" = "focus_hover" ]; then
        HDELAY=$(grep '^HOVER_DELAY=' "$CONF" 2>/dev/null | cut -d= -f2)
        [ -z "$HDELAY" ] && HDELAY="250"
        "$PATCHER" "$XPID" focus_hover "$HDELAY" >/dev/null 2>&1
      else
        "$PATCHER" "$XPID" "$WANT_FOC" >/dev/null 2>&1
      fi
      last_foc="$WANT_FOC"
    fi
  fi
  sleep 2
done
