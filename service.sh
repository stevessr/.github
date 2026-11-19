#!/system/bin/sh
MODDIR=${0%/*}
WINCTL="$MODDIR/system/bin/winctl"

i=0
while [ $i -lt 30 ]; do
  if [ "$(getprop sys.boot_completed 2>/dev/null)" = "1" ] && \
     [ -n "$(pidof com.picoxr.xrshell 2>/dev/null)" ]; then
    break
  fi
  sleep 1
  i=$((i + 1))
done

chmod 755 "$MODDIR/system/bin/winctl" "$MODDIR/system/bin/winscale_patch" 2>/dev/null
sh "$WINCTL" apply >/dev/null 2>&1
