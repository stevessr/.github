#!/system/bin/sh
CUR=$(settings get global pico_vr_multiwindow 2>/dev/null)
[ "$CUR" = "0" ] && NEXT=1 || NEXT=0
settings put global pico_vr_multiwindow "$NEXT" 2>/dev/null
mkdir -p /data/adb/pico_vr_multiwindow
touch /data/adb/pico_vr_multiwindow/config
if grep -q '^ENABLED=' /data/adb/pico_vr_multiwindow/config 2>/dev/null; then
  sed -i "s|^ENABLED=.*|ENABLED=$NEXT|" /data/adb/pico_vr_multiwindow/config
else
  echo "ENABLED=$NEXT" >> /data/adb/pico_vr_multiwindow/config
fi
if [ "$NEXT" = "1" ]; then
  echo "已开启：VR 游戏内保留多 2D 窗口"
else
  echo "已关闭：恢复 PICO 原厂单窗口策略"
fi
