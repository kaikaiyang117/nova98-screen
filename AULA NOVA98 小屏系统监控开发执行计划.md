# AULA NOVA98 小屏系统监控开发执行计划

## 1. 项目目标

开发一个独立的 NOVA98 键盘小屏控制程序，将电脑运行状态显示到键盘自带的 1.14 英寸彩色屏幕上。

第一阶段重点显示：

- 当前时间
- CPU 使用率
- 内存使用率
- CPU 温度
- 可选 GPU 使用率
- 可选 GPU 温度
- 可选网络上传/下载速率
- 可选电池状态

最终目标：

```text
┌────────────────────────┐
│  01:32          SYSTEM │
│                        │
│ CPU   █████░░   62%    │
│ TEMP  ████░░░   58°C   │
│ RAM   ██████░   74%    │
│                        │
│ ↓ 3.2 MB/s ↑ 0.8 MB/s │
└────────────────────────┘
```

屏幕物理分辨率暂按：

```text
240 × 135
RGB565
```

处理。

必须先通过实际 USB 枚举和协议验证确认，禁止在没有验证的情况下假定 NOVA98 与其他狼蛛型号协议完全一致。

---

# 2. 开发原则

整个项目按照以下顺序推进：

```text
设备识别
   ↓
协议验证
   ↓
安全上传单帧
   ↓
渲染静态 Dashboard
   ↓
读取系统数据
   ↓
动态生成 Dashboard
   ↓
低频自动刷新
   ↓
性能与 Flash 写入优化
   ↓
跨平台适配
```

不要跳过前面的阶段。

特别禁止：

```text
未确认 HID 接口
    ↓
直接运行 F108 Pro 上传命令
    ↓
大量写入设备
```

因为键盘小屏资源可能位于 SPI Flash，不正确的地址、长度或帧数可能破坏键盘内置屏幕资源。

---

# 3. 技术栈

第一版统一使用：

```text
Python 3.11+
```

依赖建议：

```text
hidapi
Pillow
psutil
pyyaml
```

后续根据操作系统增加：

Linux：

```text
psutil
lm-sensors
/sys/class/thermal
```

macOS：

```text
psutil
powermetrics
ioreg
```

Windows：

```text
psutil
LibreHardwareMonitor
WMI
```

第一阶段不要引入 Electron、Qt、Web UI。

先把：

```text
系统数据 → PNG → 键盘屏幕
```

整个闭环跑通。

---

# 4. 项目目录设计

创建：

```text
nova98-screen/
│
├── README.md
├── pyproject.toml
├── requirements.txt
│
├── docs/
│   ├── protocol.md
│   ├── hardware.md
│   ├── reverse-engineering.md
│   └── architecture.md
│
├── scripts/
│   ├── enumerate_hid.py
│   ├── probe_device.py
│   ├── test_single_frame.py
│   └── dump_metrics.py
│
├── nova98/
│   │
│   ├── __init__.py
│   │
│   ├── device/
│   │   ├── discovery.py
│   │   ├── hid_device.py
│   │   ├── protocol.py
│   │   └── profiles.py
│   │
│   ├── display/
│   │   ├── framebuffer.py
│   │   ├── rgb565.py
│   │   ├── image_encoder.py
│   │   └── uploader.py
│   │
│   ├── metrics/
│   │   ├── base.py
│   │   ├── cpu.py
│   │   ├── memory.py
│   │   ├── temperature.py
│   │   └── network.py
│   │
│   ├── renderer/
│   │   ├── renderer.py
│   │   ├── widgets.py
│   │   └── themes.py
│   │
│   ├── scheduler/
│   │   ├── refresh.py
│   │   └── change_detector.py
│   │
│   └── cli.py
│
├── layouts/
│   └── system.yaml
│
└── tests/
    ├── test_rgb565.py
    ├── test_framebuffer.py
    ├── test_metrics.py
    └── test_renderer.py
```

硬件控制代码和系统监控代码必须分离。

---

# 5. Phase 0：建立安全基线

## 目标

确保所有后续操作都不会在未知情况下修改键盘。

## Agent 任务

首先创建：

```text
docs/hardware.md
```

记录：

```text
型号：
AULA NOVA98

连接模式：
USB 有线

屏幕：
1.14 英寸 TFT

预期分辨率：
240 × 135

预期像素格式：
RGB565

已知 GIF 上限：
141 帧

协议状态：
尚未验证
```

同时明确：

```text
所有 probe 默认只读。
任何 USB 写操作必须显式调用 upload/test 命令。
```

代码中不得在：

```python
import nova98
```

或者：

```python
Nova98Device()
```

初始化时自动发送任何 USB 数据。

---

# 6. Phase 1：USB / HID 设备识别

这是整个项目最重要的第一步。

## 目标

确认 NOVA98 的：

```text
VID
PID
Manufacturer
Product
Serial
HID Interface
Usage Page
Usage
Report Size
```

## Agent 实现

创建：

```text
scripts/enumerate_hid.py
```

使用：

```python
hid.enumerate()
```

打印全部 HID interface。

输出至少包含：

```text
VID
PID
interface_number
usage_page
usage
product_string
manufacturer_string
path
```

例如：

```text
Device
--------------------------------
VID:PID       0C45:800A
Manufacturer  SONiX
Product       AULA NOVA98
Interface     3
Usage Page    FF13
Usage         0001
```

所有结果同时保存：

```text
device_dump.json
```

---

## 验收条件

运行：

```bash
python scripts/enumerate_hid.py
```

能够明确找到 NOVA98。

Agent 此时必须更新：

```text
docs/hardware.md
```

填入真实：

```text
VID
PID
Interface
Usage Page
```

不要继续使用猜测值。

---

# 7. Phase 2：判断是否兼容现有 SONiX TFT 协议

## 目标

比较 NOVA98 和已有 AULA F108 Pro TFT 协议。

重点检查是否存在类似：

```text
Usage Page FF13
Usage Page FF68
```

或者功能类似的两个 HID Interface。

预期：

```text
Control HID
    ↓
命令、ACK

LCD HID
    ↓
4096 Byte Pixel Transfer
```

---

## Agent 任务

阅读和分析以下开源项目：

```text
kitan-shiragami/aula-tft-uploader
parsiya/f108-pro
```

重点研究：

```text
DeviceProfile
Feature Report
LCD Endpoint
Start transfer
Image description
Page transfer
ACK
Apply
```

不要复制整个项目。

形成：

```text
docs/protocol.md
```

记录：

```text
F108 Pro 已知协议
NOVA98 实际 USB Descriptor
两者相同点
两者不同点
协议兼容性判断
```

---

# 8. Phase 3：实现 DeviceProfile

建立：

```python
@dataclass(frozen=True)
class DeviceProfile:
    name: str

    vendor_id: int
    product_id: int

    control_usage_page: int | None
    display_usage_page: int | None

    width: int
    height: int

    max_frames: int
```

真实 NOVA98 Profile：

```python
NOVA98 = DeviceProfile(
    name="AULA NOVA98",

    vendor_id=<实际VID>,
    product_id=<实际PID>,

    control_usage_page=<实际值>,
    display_usage_page=<实际值>,

    width=240,
    height=135,

    max_frames=141,
)
```

其中：

```text
VID/PID/Usage Page
```

必须来自真实设备。

---

# 9. Phase 4：实现纯软件 RGB565 Encoder

这一阶段不要连接键盘。

## 输入

```text
PIL.Image
```

## 输出

```text
RGB565 byte buffer
```

实现：

```text
nova98/display/rgb565.py
```

RGB888：

```text
R 8bit
G 8bit
B 8bit
```

转换：

```text
RRRRRGGG GGGBBBBB
```

即：

```python
rgb565 = (
    ((r & 0xF8) << 8)
    | ((g & 0xFC) << 3)
    | (b >> 3)
)
```

---

## 测试

至少生成：

```text
black.png
white.png
red.png
green.png
blue.png
gradient.png
```

测试：

```text
240 × 135 × 2
=
64800 bytes
```

---

## 验收条件

必须存在自动测试：

```bash
pytest
```

验证：

```text
黑色
白色
RGB
Buffer length
Byte order
```

---

# 10. Phase 5：实现静态 Dashboard Renderer

先不读取真实 CPU 数据。

创建：

```text
nova98/renderer/renderer.py
```

生成：

```text
240×135 PIL.Image
```

第一版界面：

```text
┌────────────────────────┐
│ SYSTEM           01:32 │
├────────────────────────┤
│ CPU    █████░░    62%  │
│ TEMP   ████░░░    58°  │
│ RAM    ██████░    74%  │
│                        │
│ ↓3.2M          ↑0.8M   │
└────────────────────────┘
```

先固定假数据：

```python
cpu = 62
memory = 74
temperature = 58
download = 3.2
upload = 0.8
```

生成：

```text
dashboard-preview.png
```

---

# 11. UI 设计要求

屏幕只有：

```text
240 × 135
```

不要按照桌面 GUI 思路设计。

优先：

```text
大字号
高对比度
少文本
少装饰
固定布局
```

建议区域：

```text
Header       24px

CPU          25px
Temperature  25px
Memory       25px

Footer       25px
```

剩余空间作为：

```text
margin
separator
```

进度条宽：

```text
100～120px
```

避免细线。

---

# 12. Phase 6：第一次真实屏幕上传

这是第一个危险阶段。

必须使用：

```text
纯黑
```

或非常简单的：

```text
黑底 + NOVA98 TEST
```

只上传：

```text
1 Frame
```

禁止 GIF。

禁止循环上传。

禁止突破官方协议的任何限制。

---

## 上传流程

如果协议兼容 F108 Pro，按照：

```text
START
↓
IMAGE_DESCRIPTOR
↓
16 × 4096 Byte
↓
APPLY
```

实现。

一帧：

```text
Header
256 Bytes

+

Pixel
64800 Bytes

=
65056 Bytes
```

然后补齐到：

```text
65536 Bytes
```

即：

```text
16 × 4096
```

---

# 13. 关键安全规则

必须写入代码：

```python
MAX_TEST_FRAMES = 1
```

初始开发阶段：

```python
if frame_count != 1:
    raise SafetyError(...)
```

同时：

```python
if width != 240 or height != 135:
    raise SafetyError(...)
```

以及：

```python
if payload_size > EXPECTED_MAX:
    raise SafetyError(...)
```

不要允许测试工具随意发送原始地址。

禁止提供：

```text
raw_flash_write(address, data)
```

这样的公共接口。

---

# 14. Phase 7：CPU 与内存采集

现在再进入系统监控部分。

建立统一数据模型：

```python
@dataclass
class SystemMetrics:
    cpu_percent: float | None

    memory_percent: float | None

    cpu_temperature: float | None

    gpu_percent: float | None
    gpu_temperature: float | None

    download_bytes_per_sec: float | None
    upload_bytes_per_sec: float | None

    timestamp: datetime
```

---

## CPU

使用：

```python
psutil.cpu_percent(interval=None)
```

注意：

第一次调用可能没有意义。

程序启动时：

```python
psutil.cpu_percent(None)
```

之后间隔至少：

```text
1 秒
```

采样。

---

## 内存

使用：

```python
psutil.virtual_memory()
```

取：

```python
memory.percent
```

---

# 15. Phase 8：温度采集

温度必须做成：

```text
Platform Adapter
```

不要把平台相关逻辑塞到 renderer。

统一接口：

```python
class TemperatureProvider:
    def get_cpu_temperature(self) -> float | None:
        ...
```

---

## Linux

优先：

```python
psutil.sensors_temperatures()
```

其次：

```text
/sys/class/thermal
```

或者：

```text
lm-sensors
```

---

## macOS

不要假设：

```python
psutil.sensors_temperatures()
```

一定可用。

单独实现：

```text
MacOSTemperatureProvider
```

可选：

```text
powermetrics
```

或者其他本地硬件监控数据源。

如果系统权限无法稳定读取：

```text
cpu_temperature = None
```

UI 应自动隐藏这一行，而不是报错。

---

## Windows

建立：

```text
WindowsTemperatureProvider
```

优先考虑：

```text
LibreHardwareMonitor
```

作为传感器后端。

不要直接假定 Windows WMI 一定能读取 CPU Package Temperature。

---

# 16. Phase 9：网络速率

使用：

```python
psutil.net_io_counters()
```

记录：

```text
t0 rx0 tx0
```

下一周期：

```text
t1 rx1 tx1
```

计算：

```text
download =
(rx1 - rx0) / dt

upload =
(tx1 - tx0) / dt
```

提供自动单位：

```text
KB/s
MB/s
GB/s
```

---

# 17. Phase 10：Metrics Service

建立：

```text
nova98/metrics/service.py
```

职责只有：

```text
采集系统状态
```

不能操作屏幕。

运行频率：

```text
1 秒一次
```

例如：

```text
MetricsService
      │
      ├ CPU
      ├ RAM
      ├ Temp
      └ Network
```

形成：

```text
SystemMetrics
```

---

# 18. Phase 11：Renderer 与 Metrics 对接

调用：

```python
metrics = metrics_service.read()

image = renderer.render(metrics)
```

得到：

```text
240×135 Image
```

第一阶段先：

```text
每秒生成 PNG
```

但：

```text
不要每秒传给键盘。
```

这样可以先验证监控数据和 UI。

---

# 19. Phase 12：设计刷新策略

这是整个项目非常重要的一点。

键盘 TFT 很可能不是实时 framebuffer，而是：

```text
PC
 ↓
SPI Flash
 ↓
TFT
```

因此不能按照：

```text
60 FPS
30 FPS
1 FPS
```

持续刷。

第一版默认：

```text
屏幕最短刷新周期：
30 秒
```

建议：

```python
MIN_REFRESH_INTERVAL = 30
```

---

# 20. Change Detector

不要单纯：

```text
每 30 秒无脑刷新
```

实现：

```text
nova98/scheduler/change_detector.py
```

只有变化达到阈值才更新。

例如：

CPU：

```text
变化 > 10%
```

RAM：

```text
变化 > 5%
```

温度：

```text
变化 > 3°C
```

网络状态：

```text
变化超过设定档位
```

时间：

```text
每分钟
```

最终策略：

```text
if elapsed < 30s:
    不更新

elif significant_change:
    更新

elif elapsed > 5min:
    强制更新
```

---

# 21. 推荐刷新逻辑

第一阶段：

```text
Metrics sampling
        1s
        ↓
Change Detection
        ↓
Refresh Decision
        ↓
至少间隔 30s
        ↓
Renderer
        ↓
Uploader
```

因此：

```text
采样快
屏幕刷新慢
```

这是正确设计。

---

# 22. Phase 13：缓存与 Diff

渲染完成后：

```python
frame_hash = sha256(frame_buffer)
```

如果：

```text
new_hash == previous_hash
```

直接：

```text
skip upload
```

避免无意义 Flash 写入。

---

# 23. Phase 14：CLI

最终至少支持：

```bash
nova98-screen devices
```

打印：

```text
NOVA98
VID
PID
HID interfaces
```

---

```bash
nova98-screen metrics
```

打印：

```text
CPU        34%
RAM        61%
TEMP       54°C
DOWNLOAD   2.3MB/s
UPLOAD     330KB/s
```

---

```bash
nova98-screen preview
```

生成：

```text
preview.png
```

---

```bash
nova98-screen show
```

发送一次 Dashboard。

---

```bash
nova98-screen run
```

启动后台刷新循环。

---

# 24. Phase 15：配置文件

创建：

```yaml
display:

  refresh:
    min_interval: 30
    force_interval: 300

metrics:

  cpu: true
  memory: true
  temperature: true
  network: true

thresholds:

  cpu: 10

  memory: 5

  temperature: 3

layout:

  name: system
```

文件：

```text
config.yaml
```

---

# 25. Phase 16：异常处理

必须正确处理：

## 键盘拔掉

不要退出整个程序。

状态：

```text
CONNECTED
   ↓
DISCONNECTED
   ↓
RECONNECTING
```

每：

```text
5 秒
```

重新枚举设备。

---

## 无法读取温度

输出：

```text
temperature = None
```

屏幕自动调整布局。

---

## USB 上传失败

不要无限重试。

最大：

```text
3 次
```

之后进入：

```text
BACKOFF
```

---

## 键盘进入无线模式

识别：

```text
USB LCD device unavailable
```

程序继续运行 Metrics Service，但是暂停上传。

---

# 26. Phase 17：日志

至少输出：

```text
logs/nova98-screen.log
```

记录：

```text
Device connected
Device disconnected

Metrics collected

Frame rendered

Frame skipped

Frame upload started

Frame upload finished

Upload failed
```

默认不要打印：

```text
完整 64KB RGB payload
```

Debug 模式才允许输出协议摘要。

---

# 27. Phase 18：自动测试

必须覆盖纯软件部分。

测试：

```text
RGB565 conversion

Frame dimensions

Frame size

Dashboard renderer

CPU metric

Memory metric

Network speed calculation

Change detector

Refresh limiter

Config parser
```

硬件测试单独标记：

```text
@pytest.mark.hardware
```

不能：

```bash
pytest
```

就自动往键盘写数据。

硬件测试必须明确：

```bash
pytest -m hardware
```

才执行。

---

# 28. Phase 19：Agent 每阶段提交要求

Agent 不要一次写完所有功能。

推荐提交顺序：

```text
commit 1
chore: initialize nova98 screen project
```

```text
commit 2
feat: add HID device discovery
```

```text
commit 3
docs: document NOVA98 HID interfaces
```

```text
commit 4
feat: implement RGB565 framebuffer encoding
```

```text
commit 5
feat: add static system dashboard renderer
```

```text
commit 6
feat: implement safe single-frame uploader
```

这里必须人工确认：

```text
屏幕成功显示测试图片
```

确认后继续。

```text
commit 7
feat: add system metrics collection
```

```text
commit 8
feat: add platform temperature providers
```

```text
commit 9
feat: connect metrics to dashboard renderer
```

```text
commit 10
feat: add refresh scheduler and change detection
```

```text
commit 11
feat: add CLI and runtime daemon
```

---

# 29. Agent 必须遵守的停止条件

以下情况下停止硬件写操作：

### 情况 1

实际：

```text
VID/PID
```

和已有协议完全不同。

---

### 情况 2

找不到预期 LCD HID Interface。

---

### 情况 3

发送初始化命令后 ACK 不符合预期。

---

### 情况 4

上传第一块数据出现：

```text
timeout
device reset
USB disconnect
unknown response
```

---

### 情况 5

键盘屏幕出现：

```text
乱码
内置菜单异常
屏幕异常
```

此时：

```text
立即停止任何 Flash 写入。
```

保留抓包数据进一步分析。

---

# 30. 如果现有协议不兼容

不要猜。

进入：

```text
Protocol Reverse Engineering
```

优先级：

```text
WebHID Hook
    ↓
USBPcap / Wireshark
    ↓
Firmware Reverse Engineering
```

优先观察官方 A HUB：

```text
上传纯黑 PNG

上传纯红 PNG

上传纯绿 PNG

上传纯蓝 PNG
```

比较：

```text
Feature Reports
Output Reports
Endpoint
Packet Size
Header
Payload
ACK
```

建立：

```text
docs/reverse-engineering.md
```

只有协议明确后才重新实现 uploader。

---

# 31. MVP 验收标准

第一版完成时必须达到：

```text
[1] 自动识别 NOVA98

[2] 能读取 CPU 使用率

[3] 能读取内存使用率

[4] 尽可能读取 CPU 温度

[5] 能计算网络速率

[6] 能生成 240×135 Dashboard

[7] 能生成 RGB565 Frame

[8] 能安全上传单帧

[9] 能在键盘屏幕显示系统状态

[10] 可以后台运行

[11] 键盘拔插不会导致程序崩溃

[12] 不会高频写 SPI Flash
```

---

# 32. 第一版明确不做

暂时不要开发：

```text
视频播放

高帧率动画

音频频谱

实时歌词

触摸交互

Electron GUI

Web Dashboard

云同步

插件市场

复杂 Widget SDK
```

这些都会显著扩大项目范围。

第一版唯一目标：

```text
System Metrics
      ↓
Dashboard
      ↓
NOVA98 TFT
```

把这个链路做稳定。

---

# 33. 第二阶段规划

MVP 成功以后，再扩展：

```text
Spotify / Apple Music
```

显示：

```text
封面
歌曲名
歌手
播放状态
```

---

增加：

```text
GitHub
```

显示：

```text
CI Passed
CI Failed
PR
Issue
```

---

增加开发状态：

```text
Git Branch

Docker

Build Status

Agent Running

Token Usage
```

最终形成：

```text
┌──────────────────────┐
│ NOVA98 Screen Engine │
└───────────┬──────────┘
            │
      Widget Engine
            │
 ┌──────────┼──────────┐
 │          │          │
System     Music      Dev
 │          │          │
CPU        Song       Git
RAM        Album      CI
Temp                  Agent
```

---

# 34. 后期正确的软件架构

建议演化成：

```text
                  Data Providers

       ┌─────────────┼─────────────┐
       │             │             │

     System        Music         GitHub

       │             │             │
       └─────────────┼─────────────┘
                     ↓

               Metrics / State

                     ↓

                 Widgets

                     ↓

                  Layout

                     ↓

                 Renderer

                     ↓

              PIL RGB Image

                     ↓

              RGB565 Encoder

                     ↓

             Display Backend

                     ↓

              NOVA98 HID
```

注意：

```text
Widget
```

永远不能直接访问：

```text
USB HID
```

这样以后即使换键盘，也只需要更换：

```text
DisplayBackend
```

---

# 35. 给 Agent 的执行总指令

按照以下规则执行项目：

1. 首先完成 USB HID 枚举，禁止直接写入键盘。

2. 所有 VID、PID、Usage Page、Interface Number 必须来自实际设备，不允许凭已有 F108 Pro 数据硬编码 NOVA98。

3. 优先验证 NOVA98 是否兼容已有 AULA/SONiX TFT 协议。

4. 协议未确认以前禁止批量上传、GIF 上传和原始 Flash 写操作。

5. 第一阶段上传测试严格限制为单帧。

6. 屏幕尺寸暂按 240×135，但必须通过设备或官方协议进一步确认。

7. 系统监控模块和 HID 驱动必须解耦。

8. Renderer 只接收 SystemMetrics，不允许直接读取 psutil。

9. Uploader 只接收 framebuffer，不关心 CPU、内存等业务数据。

10. 温度读取必须采用平台 Adapter，不允许假定所有系统都支持 psutil temperature。

11. Metrics 可以每秒采样，但屏幕默认最短刷新间隔不得低于 30 秒。

12. 使用 ChangeDetector 和 Frame Hash 避免无意义刷新。

13. 所有硬件写测试必须显式执行，普通单元测试不得访问键盘。

14. 每完成一个阶段运行测试并提交 Git Commit。

15. 如果协议行为与预期不一致，不要继续猜测，停止写入并进入协议抓包分析。

16. 不要为了“一步到位”提前开发 GUI、音乐、天气或复杂插件系统。

当前第一优先级只有：

```text
识别 NOVA98
      ↓
成功显示一张自己生成的静态图片
      ↓
显示 CPU / RAM / 温度
      ↓
实现安全自动更新
```

---

# 36. Agent 当前立即执行的任务

现在开始只执行以下工作：

```text
Task 1
初始化 nova98-screen Python 项目。

Task 2
实现 HID Enumerator。

Task 3
要求用户将 NOVA98 切换到 USB 有线模式并执行 Enumerator。

Task 4
分析真实 HID Descriptor。

Task 5
与 aula-tft-uploader / f108-pro 协议进行比对。

Task 6
生成 docs/protocol.md。

Task 7
如果确认兼容，再实现单帧 RGB565 上传。

Task 8
成功显示静态测试图以后，再开始 CPU / RAM / 温度模块。
```

在 Task 7 完成之前，不得开始后台自动刷新功能。