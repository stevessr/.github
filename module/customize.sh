#!/system/bin/sh
ui_print "- PICO VR Multi-Window 2D v1.0.0"
DEV=$(getprop ro.product.device 2>/dev/null)
if [ "$DEV" != "sparrow" ]; then
  ui_print "! 警告：当前设备为 $DEV，本补丁基于 PICO 4 Ultra (sparrow) services.jar 构建"
fi
ui_print "- 已安装 services.jar 多窗口补丁与 SukiSU WebUI"
ui_print "- 提示：临时 root 设备请使用 SukiSU Nova 软重启以加载补丁"
