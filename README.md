# PICO FPS Control v1.2.0

PICO 4 Ultra 刷新率解锁 + 智能帧率 + 风扇控制 + 可视化温度曲线。

## 功能

| 功能 | 说明 |
|---|---|
| 60 / 72 / 90 fps | 稳定锁定（非抖动） |
| 🔥 狂暴模式 | 风扇 100% + 锁 90fps |
| 遵从系统默认 | 移除全部补丁，风扇 50%，帧率交给系统 |
| 自动模式 | 视频类 App → 60fps，其它 → 72fps |
| 🌡️ 温度曲线可视化 | SVG 拖拽四点，实时预览，保存即生效 |
| 风扇手动 | 滑条 0-100%，stationservice code 121 |
| 自愈 | pxrhmdservice 重启后 10s 内自动重打补丁 |
| 看门狗 | daemon 被杀 3s 后自动重启 |
| WebUI | KernelSU 模块页内图形界面 |

## 用法

```bash
fpsctl status     # 状态
fpsctl set 60     # 锁 60fps
fpsctl set 90     # 锁 90fps
fpsctl auto       # 智能
fpsctl curve      # 温度曲线
fpsctl default    # 遵从系统默认
fpsctl off        # 恢复系统默认 + 停守护
```

配置 /data/adb/pico_fps/config：
```
MODE=fixed|auto|curve|default|off
FPS=60|72|90
CURVE=45,50,55,60,90,72,60,45
```

## 原理

三层锁逐个解开：
1. 白名单：BaseDevice::checkRefreshRateValid 补丁（file off 0x399e8）
2. 回弹：HawkDev::setRefreshRate 入参强制改写（file off 0x3a198）
3. 过渡引擎：保持原逻辑，只改入参

## 风扇控制

发现 PICO 风扇的真实控制通道：**stationservice (PicoStation-new) code 121 = SetFanSpeed(int 0-100)**。
- service call PicoStation-new 121 i32 100 = 风扇 100%
- code 120 = 读当前档位

## 实测（YouTube VR）

| 档位 | GPU占用 | GPU频率 | GPU温度 | 帧时间 |
|---|---|---|---|---|
| 60fps | 81% | 285MHz | 52.8°C | 16.67ms |
| 72fps原生 | 86% | 317MHz | 56.5°C | 13.36ms |
| 90fps | 80% | 492MHz | 52.8°C | 10.69ms |

90fps：帧率 +25%，帧时间 -20%，GPU 温度 -3.7°C。

## 限制

- 依赖临时 root（DF 越狱），重启后需重新越狱
- 狂暴模式会锁 90fps + 风扇 100%，风噪大耗电高
- 90fps 模式会强制所有 setRefreshRate 请求为 90

## 卸载

fpsctl off && fpsd-stop
rm -rf /data/adb/modules/pico_fps_control /data/adb/pico_fps
