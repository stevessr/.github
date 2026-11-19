#!/system/bin/sh
# KSU 模块 action 按钮：快速切换帧率
BIN=/data/adb/modules/pico_fps_control/system/bin
echo "=== PICO 帧率控制 ==="
$BIN/fpsctl status
echo ""
echo "1) 60fps (省电)"
echo "2) 72fps (默认)"
echo "3) 90fps (性能)"
echo "4) 自动模式"
echo "5) 关闭控制"
echo ""
read -p "选择: " c
case "$c" in
  1) $BIN/fpsctl set 60 ;;
  2) $BIN/fpsctl set 72 ;;
  3) $BIN/fpsctl set 90 ;;
  4) $BIN/fpsctl auto ;;
  5) $BIN/fpsctl off ;;
esac
sleep 2
$BIN/fpsctl status
