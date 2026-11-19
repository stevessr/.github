#!/system/bin/sh
settings delete global pico_vr_multiwindow 2>/dev/null
settings delete global pico_vr_force_resize 2>/dev/null
settings delete global pico_vr_overlay_bridge 2>/dev/null
settings delete global pico_vr_overlay_bridge_deny 2>/dev/null
settings put system pvr.xrshell.overlay_panel_count 5 2>/dev/null
rm -rf /data/adb/pico_vr_multiwindow
