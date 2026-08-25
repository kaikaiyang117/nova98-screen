# nova98-screen

AULA NOVA98 键盘小屏系统监控：将 CPU / 内存 / 温度 / 网络速率渲染成 240×135
Dashboard 并通过 USB HID 上传到键盘 TFT 屏幕显示。

## 状态

- ✅ 设备识别（`0x38A6:0x273B`）
- ✅ 协议逆向完成（来源：官方 AULA HUB WebHID JS，见 `docs/protocol.md`）
- ✅ 单帧上传验证成功（屏幕实机确认）
- ✅ 系统指标采集 + 安全自动刷新（最短 30s，变化检测 + 帧哈希去重）

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python -m nova98.cli devices         # 列出 NOVA98 HID 接口
python -m nova98.cli metrics         # 打印当前系统指标
python -m nova98.cli telemetry       # 打印原生遥测通道将发送的值
python -m nova98.cli preview         # 生成 preview.png 预览图
python -m nova98.cli show            # 手动上传一次静态帧到屏幕
python -m nova98.cli telemetry-test  # 单次发送 cmd 52 测试（--dry-run 可只编码）
python -m nova98.cli run             # 双通道后台运行（遥测 1Hz + 静态 30s）
```

配置文件 `config.yaml`（模板见 `layouts/system.yaml`）：刷新间隔、指标开关、
变化阈值。

## 架构（双通道）

```text
                    System

                      │

                MetricsService (1s)

                      │
             ┌────────┴────────┐
             │                 │

          Fast Path         Slow Path

             │                 │

      CPU/GPU/Temp       RAM/Network/UI

             │                 │

      Native Telemetry      Renderer

          cmd 52          Framebuffer

             │            TFT Upload

             └────────┬────────┘

                   NOVA98
```

- **Native Telemetry (cmd 52)**：协议已逆向并验证（ACK 正常），但
  **NOVA98 固件不做任何渲染，官方 HUB 也从未对该型号调用此命令**
  （详见 `docs/native-telemetry.md`）。实现保留，默认关闭。
- **Static Frame (cmd 80)**：CPU / 温度 / RAM / 网络全部经 240×135 帧
  渲染上传，默认最短 30s，相对"最后成功上屏状态"判断变化 + 帧哈希去重。
  不含时钟（避免每分钟写 Flash）。

硬件驱动与业务数据完全解耦；所有写操作仅在显式命令中发生。

## 测试

```bash
pytest              # 纯软件测试（默认排除硬件标记用例）
```

## 文档

- `docs/hardware.md` — 实测设备信息与安全基线
- `docs/protocol.md` — NOVA98 完整协议（逆向自 AULA HUB）
- `docs/reverse-engineering.md` — 探测过程记录

## 安全说明

上传会写入键盘 SPI Flash。工具内置护栏：单帧限制、尺寸校验、页数上限、
无原始地址接口。若屏幕出现乱码或内置菜单异常，请立即停止使用并拔电重启键盘。
