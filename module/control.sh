#!/system/bin/sh
# 临时 root 挂载管理：在全局 mount namespace (PID 1) 中 bind-mount services.jar
export PATH=/system/bin:/vendor/bin:/data/adb/ksu/bin:$PATH
SELF=$(readlink -f "$0")
MODDIR=${SELF%/*}
ACTION=${1:-status}
BB=/data/adb/ksu/bin/busybox
SRC="$MODDIR/system/framework/services.jar"
DST="/system/framework/services.jar"

[ "$(id -u)" = "0" ] || { echo "need root"; exit 1; }
[ "${2:-}" = "global" ] || exec "$BB" nsenter -t 1 -m /system/bin/sh "$SELF" "$ACTION" global

is_mounted() {
  awk -v t="$DST" '$5==t{ok=1} END{exit !ok}' /proc/self/mountinfo
}

case "$ACTION" in
  mount|start)
    [ -f "$SRC" ] || { echo "missing $SRC"; exit 2; }
    chown 0:0 "$SRC" 2>/dev/null
    chmod 644 "$SRC" 2>/dev/null
    chcon u:object_r:system_file:s0 "$SRC" 2>/dev/null
    if ! is_mounted; then
      mount --bind "$SRC" "$DST" || { echo "mount failed"; exit 3; }
    fi
    P=$(pidof com.picoxr.xrshell 2>/dev/null)
    [ -n "$P" ] && [ -x "$MODDIR/system/bin/xrshell_dist_patch" ] && "$MODDIR/system/bin/xrshell_dist_patch" "$P" patch >/dev/null 2>&1
    echo "MOUNTED: $DST"
    ;;
  umount|stop)
    P=$(pidof com.picoxr.xrshell 2>/dev/null)
    [ -n "$P" ] && [ -x "$MODDIR/system/bin/xrshell_dist_patch" ] && "$MODDIR/system/bin/xrshell_dist_patch" "$P" restore >/dev/null 2>&1
    if is_mounted; then
      umount -l "$DST"
      echo "UNMOUNTED: $DST"
    else
      echo "NOT_MOUNTED"
    fi
    ;;
  status)
    if is_mounted; then
      echo "MOUNTED"
    else
      echo "NOT_MOUNTED"
    fi
    ;;
  *)
    echo "usage: control.sh mount|umount|status"
    ;;
esac
