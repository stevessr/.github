#!/system/bin/sh
MODDIR=${0%/*}
WINCTL="$MODDIR/system/bin/winctl"

echo "=== PICO 2D 窗口缩放与距离控制 ==="
sh "$WINCTL" status
echo ""
echo "1) 推荐预设 (最大距离 60m, 最大尺寸 6400x3600 / 4x)"
echo "2) 巨幕影院 (最大距离 100m, 最大尺寸 7680x4320 / 4.8x)"
echo "3) 极限模式 (最大距离 200m, 最大尺寸 9600x5400 / 6x)"
echo "4) 还原原厂 (最大距离 12m, 最大尺寸 2400x1350 / 1.5x)"
echo ""
read -p "请选择 [1-4]: " c
case "$c" in
  1) sh "$WINCTL" preset default ;;
  2) sh "$WINCTL" preset cinema ;;
  3) sh "$WINCTL" preset extreme ;;
  4) sh "$WINCTL" preset stock ;;
  *) echo "未更改" ;;
esac
sleep 1
sh "$WINCTL" status
