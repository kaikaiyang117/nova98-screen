# nova98-screen

AULA NOVA98 键盘小屏系统监控：将 CPU / 内存 / 温度 / 网络速率渲染成 240×135
Dashboard，通过 USB HID (cmd 80) 上传到键盘 TFT 屏幕显示。

## 当前稳定能力

```text
✅ NOVA98 HID 识别（0x38A6:0x273B）
✅ AULA HUB 协议逆向
✅ 240×135 RGB565 framebuffer
✅ 单帧实机上传（cmd 80）
✅ CPU / RAM / CPU 温度 / 网络采集
✅ 静态 Dashboard 渲染
✅ 变化阈值刷新（相对最后成功上屏状态）
✅ Frame Hash 去重
✅ USB 重连 / 失败退避
✅ cmd 52 协议实现（实验性）
```

⚠️ **cmd 52（Native Telemetry）**：设备返回 ACK 但 NOVA98 固件不渲染任何内容，
官方 HUB 也从未对该型号使用。默认关闭；实现保留用于未来固件/其他型号。

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python -m nova98.cli devices         # 列出 NOVA98 HID 接口
python -m nova98.cli metrics         # 打印当前系统指标
python -m nova98.cli telemetry       # 实验性：显示 cmd 52 将发送的值
python -m nova98.cli preview         # 生成 preview.png 预览图
python -m nova98.cli show            # 手动上传一次静态帧
python -m nova98.cli telemetry-test  # 实验性协议诊断（单次发送 / --dry-run）
python -m nova98.cli run             # 后台监控运行时
```

配置文件 `config.yaml`（模板见 `layouts/system.yaml`）：刷新间隔、指标开关、
变化阈值。

## 架构（单一活动显示通道）

```text
                 MetricsService
                       │
                       ▼

                 SystemMetrics

                       │
                       ▼

              StaticDisplayState

                       │
                       ▼

                    Renderer

                       │
                       ▼

                 RGB565 Frame

                       │
                       ▼

                  TFT Upload
                    cmd 80

                       │
                       ▼

                    NOVA98


Experimental only:

SystemMetrics → TelemetryStatus → cmd 52 → ACK only
（当前 NOVA98 固件不渲染）
```

### Flash 写入安全不变量

- 变化检测基于**最后成功上屏的状态**（而非上次采样），缓慢漂移可累积触发
- 相同 framebuffer **永不重复上传**（force 到期也只重新评估）
- 上传失败不提交基线；连续失败进入 BACKOFF 并释放 HID
- 无时钟显示——避免为显示时间每分钟写一次 Flash

## 测试与 CI

```bash
pytest    # 纯软件测试，普通运行不访问硬件
```

GitHub Actions 在 Python 3.11/3.12/3.13 上自动运行测试套件。

## 文档

- `docs/hardware.md` — 实测设备信息与安全基线
- `docs/protocol.md` — NOVA98 完整协议（逆向自 AULA HUB）
- `docs/native-telemetry.md` — cmd 52 全部实验记录与不可用结论
- `docs/reverse-engineering.md` — 探测过程记录

## 安全说明

上传会写入键盘 SPI Flash。工具内置护栏：尺寸校验、页数上限、相同帧去重、
无原始地址接口。若屏幕出现乱码或内置菜单异常，请立即停止使用并拔电重启键盘。
