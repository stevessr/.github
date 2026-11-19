# PICO 4 Ultra 模块构建与发布

PICO 4 Ultra 临时 root 相关模块构建与发布托管。

## 模块列表

| 模块 | 版本 | 说明 | 下载 |
|---|---|---|---|
| **PICO FPS Control** | v1.2.0 | 刷新率解锁：60/72/90fps + 狂暴模式 + 风扇控制 + 可视化温度曲线 | [Releases](https://github.com/stevessr/.github/releases) |

### PICO FPS Control v1.2.0

解锁 PICO 4 Ultra 刷新率白名单。纯运行时内存补丁，不写分区。

**功能**
- 60 / 72 / 90 fps 稳定锁定（非抖动）
- 🔥 狂暴模式：风扇 100% + 锁 90fps
- 🌱 遵从系统默认：移除全部补丁，帧率交给系统
- 自动模式：视频类 App → 60fps
- 🌡️ 温度曲线可视化（SVG 拖拽编辑）
- 风扇手动滑条（stationservice code 121）
- 自愈 + 看门狗 + WebUI

**安装**
```bash
# 需先完成 DF 越狱（临时 root）
adb push pico_fps_control-v1.2.0.zip /data/local/tmp/
adb shell su -c 'mkdir -p /data/adb/modules/pico_fps_control && cd /data/adb/modules/pico_fps_control && unzip -o /data/local/tmp/pico_fps_control-v1.2.0.zip'
adb shell su -c 'chmod -R 755 /data/adb/modules/pico_fps_control/system/bin'
adb shell su -c '/data/adb/modules/pico_fps_control/service.sh &'
```

**原理**：三层锁逐个解开
1. 白名单：`BaseDevice::checkRefreshRateValid` 内存补丁（file off 0x399e8）
2. 回弹：`HawkDev::setRefreshRate` 入参强制改写（file off 0x3a198）
3. 过渡引擎：保持原逻辑，只改入参

**实测**（YouTube VR）

| 档位 | GPU占用 | GPU频率 | GPU温度 | 帧时间 |
|---|---|---|---|---|
| 60fps | 81% | 285MHz | 52.8°C | 16.67ms |
| 72fps 原生 | 86% | 317MHz | 56.5°C | 13.36ms |
| 90fps | 80% | 492MHz | 52.8°C | 10.69ms |

源码：`pico-fps-control/` 目录
