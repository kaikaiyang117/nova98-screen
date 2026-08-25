# NOVA98 Native Telemetry 实时监控通道开发执行文档

## 1. 文档目的

本文档用于指导代码 Agent 对现有 `nova98-screen` 项目实施下一阶段开发。

项目仓库：

```text
https://github.com/kaikaiyang117/nova98-screen
```

本阶段不再以“增加更多 Dashboard 指标”为主要目标，而是解决当前架构最核心的问题：

```text
当前：
系统数据变化
    ↓
重新生成 240×135 图片
    ↓
RGB565
    ↓
65056 Bytes framebuffer
    ↓
16 × 4096 Bytes HID 数据
    ↓
重新写入键盘屏幕
```

需要升级为：

```text
                  ┌────────────────────────┐
                  │ Native Telemetry 通道   │
                  │ cmd 52                 │
MetricsService ───┤ CPU/GPU/Temperature    │
                  │ 高频、临时状态更新       │
                  └────────────────────────┘
                            +
                  ┌────────────────────────┐
                  │ Static Frame 通道       │
                  │ cmd 80 / TFT Upload    │
                  │ 背景、布局、静态内容     │
                  └────────────────────────┘
```

最终形成：

```text
Static Frame + Dynamic Telemetry
```

双通道显示架构。

---

# 2. 当前仓库已完成能力

Agent 开始工作前，必须先确认当前 `main` 分支实际状态。

当前项目已经具备：

```text
✅ NOVA98 USB HID 枚举

✅ 实际 VID / PID：
   VID = 0x38A6
   PID = 0x273B
   另有可能的有线 PID = 0x275D

✅ Interface 2 / Usage Page FF68
   控制命令通道

✅ Interface 3 / Usage Page FF67
   TFT 数据通道

✅ AULA HUB WebHID 协议逆向

✅ RGB565 转换

✅ 240×135 framebuffer 构建

✅ TFT 单帧上传

✅ 每块 ACK 校验

✅ CPU / RAM / CPU 温度采集

✅ 网络速率采集

✅ Dashboard Renderer

✅ 自动刷新

✅ ChangeDetector

✅ RefreshLimiter

✅ Frame Hash 去重

✅ USB 断开重连

✅ 上传失败 Backoff
```

不得重复开发已有功能。

开始前执行：

```bash
git status
git log --oneline -15
pytest
```

确认现有测试通过。

---

# 3. 本阶段核心目标

整个阶段只有四个主要目标。

## Goal 1

修复当前：

```text
control_usage_page
display_usage_page
```

命名与实际使用语义颠倒的问题。

---

## Goal 2

实现：

```text
cmd 52
SET_TEMPORARY_COMMAND_DATA
```

中的系统监控状态数据编码和发送能力。

---

## Goal 3

通过实机实验确认：

```text
CPU Usage
CPU Temperature
GPU Usage
GPU Temperature
```

是否可以：

```text
不上传整个 framebuffer
```

直接更新屏幕显示。

---

## Goal 4

若 Goal 3 验证成功：

将当前运行架构重构为：

```text
Static Display Channel
+
Native Telemetry Channel
```

---

# 4. 非目标

本阶段明确禁止开发：

```text
Spotify

Apple Music

天气 API

GitHub Widget

Agent 状态

Pomodoro

复杂 Widget 系统

Electron GUI

Qt GUI

Web UI

插件市场

高帧率动画

实时视频

歌词

新的多页面系统
```

这些全部推迟。

本阶段唯一关注：

```text
让 CPU / GPU / 温度走键盘原生实时状态协议
```

---

# 5. 第一阶段：代码审查与现有协议一致性检查

## 5.1 必须检查文件

首先阅读：

```text
docs/protocol.md

nova98/device/profiles.py

nova98/device/hid_device.py

nova98/display/uploader.py

nova98/metrics/base.py

nova98/metrics/service.py

nova98/scheduler/daemon.py
```

不要直接开始写代码。

---

# 6. 修复 DeviceProfile 语义错误

当前真实协议定义：

```text
Interface 2
Usage Page 0xFF68
=
Control Channel


Interface 3
Usage Page 0xFF67
=
TFT Stream Channel
```

因此 Profile 必须具有正确语义：

```python
NOVA98 = DeviceProfile(
    name="AULA NOVA98",

    vendor_id=0x38A6,
    product_id=0x273B,

    control_usage_page=0xFF68,
    display_usage_page=0xFF67,

    width=240,
    height=135,

    max_frames=141,
)
```

---

## 6.1 修改 hid_device.py

当前设备打开逻辑必须最终变成：

```python
control:
    interface_number == 2
    usage_page == profile.control_usage_page
```

以及：

```python
tft:
    interface_number == 3
    usage_page == profile.display_usage_page
```

不能再通过：

```text
control → display_usage_page
display → control_usage_page
```

这种互相抵消的方式工作。

---

# 7. 增加 HID Interface 定义

为了避免以后再出现 Usage Page 和 Interface 语义错位，建议进一步增加：

```python
@dataclass(frozen=True)
class HidInterfaceProfile:
    interface_number: int
    usage_page: int
```

然后：

```python
@dataclass(frozen=True)
class DeviceProfile:
    name: str
    vendor_id: int
    product_id: int

    control: HidInterfaceProfile
    display: HidInterfaceProfile

    width: int
    height: int
    max_frames: int
```

NOVA98：

```python
NOVA98 = DeviceProfile(
    name="AULA NOVA98",
    vendor_id=0x38A6,
    product_id=0x273B,

    control=HidInterfaceProfile(
        interface_number=2,
        usage_page=0xFF68,
    ),

    display=HidInterfaceProfile(
        interface_number=3,
        usage_page=0xFF67,
    ),

    width=240,
    height=135,
    max_frames=141,
)
```

这样比单独两个 Usage Page 字段更加可靠。

如果改动成本很小，优先使用此方案。

---

# 8. Profile 修复测试

增加测试：

```text
tests/test_profiles.py
```

至少验证：

```python
assert NOVA98.control.interface_number == 2
assert NOVA98.control.usage_page == 0xFF68

assert NOVA98.display.interface_number == 3
assert NOVA98.display.usage_page == 0xFF67
```

HID mock 测试还应验证：

```text
open control
→ Interface 2

open TFT
→ Interface 3
```

---

# 9. Commit 1

完成以上工作后提交：

```text
fix: align NOVA98 HID interface profile semantics
```

此提交不得混入 Telemetry 功能。

---

# 10. 第二阶段：建立 Native Telemetry 模块

新增目录或文件：

```text
nova98/telemetry/
    __init__.py
    model.py
    encoder.py
```

如果项目规模暂时不值得独立 package，也可使用：

```text
nova98/device/telemetry.py
```

推荐独立：

```text
nova98/telemetry/
```

因为后续这会成为一条独立数据通道。

---

# 11. Telemetry 数据模型

新增：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryStatus:
    cpu_usage: int | None = None
    cpu_temperature: int | None = None

    gpu_usage: int | None = None
    gpu_temperature: int | None = None

    temperature_current: int | None = None
    temperature_high: int | None = None
    temperature_low: int | None = None

    weather_code: int | None = None
    humidity: int | None = None
```

注意：

本阶段：

```text
weather_code
humidity
```

只保留协议字段。

不要开发天气数据源。

---

# 12. cmd 52 已知 Buffer 结构

根据已经逆向得到的 AULA HUB 实际协议：

```text
Command:
52 decimal
0x34 hexadecimal

SET_TEMPORARY_COMMAND_DATA
```

系统状态 Buffer：

```text
长度：
24 bytes
```

已知关键字段：

```text
byte[6]  = 0x5A

byte[12] = CPU usage
byte[13] = CPU temperature

byte[14] = GPU usage
byte[15] = GPU temperature

byte[16] = current temperature
byte[17] = high temperature
byte[18] = low temperature

byte[19] = weather
byte[20] = humidity
```

---

# 13. 编码器实现

新增：

```python
def encode_system_status(
    status: TelemetryStatus
) -> bytes:
    ...
```

必须返回：

```text
exactly 24 bytes
```

---

## 13.1 Usage 校验

CPU/GPU Usage：

```text
0 <= value <= 100
```

如果超出：

```python
raise ValueError
```

不要静默 wrap。

---

## 13.2 Temperature 校验

温度字段为：

```text
signed int8
```

因此合法值：

```text
-128 ~ 127
```

实际 CPU/GPU 温度可以进一步限制为：

```text
-40 ~ 127
```

但编码层建议遵守协议：

```text
-128 ~ 127
```

---

## 13.3 None 的处理

不要凭感觉决定 `None` 对应什么协议值。

第一版可以规定：

```text
None → 0
```

但必须：

1. 在代码中写清楚；
2. 写进 `docs/protocol.md`；
3. 如果官方 JS 有明确默认值，则严格使用官方逻辑。

优先回查已经逆向的 AULA HUB JS。

不得自行发明：

```text
255 = unknown
```

除非官方逻辑能证明。

---

# 14. signed int8 编码

建立辅助函数：

```python
def encode_i8(value: int) -> int:
    if value < -128 or value > 127:
        raise ValueError(...)

    return value & 0xFF
```

例如：

```text
45°C
→ 0x2D

-5°C
→ 0xFB
```

---

# 15. 编码测试

新增：

```text
tests/test_telemetry_encoder.py
```

覆盖：

```text
CPU 0
CPU 50
CPU 100

GPU 0
GPU 100

Temperature +45
Temperature 0
Temperature -5

非法 CPU -1
非法 CPU 101

Temperature -129
Temperature 128

payload length = 24
```

验证关键 byte：

```python
payload = encode_system_status(
    TelemetryStatus(
        cpu_usage=63,
        cpu_temperature=55,
        gpu_usage=42,
        gpu_temperature=61,
    )
)

assert payload[6] == 0x5A

assert payload[12] == 63
assert payload[13] == 55

assert payload[14] == 42
assert payload[15] == 61
```

---

# 16. Commit 2

提交：

```text
feat: add NOVA98 native telemetry encoder
```

此时：

```text
不得发送真实 HID 数据
```

只实现纯软件层。

---

# 17. 第三阶段：实现 Telemetry HID Sender

在：

```text
nova98/device/hid_device.py
```

不要直接写 CPU/GPU 业务逻辑。

建议新增：

```python
def send_temporary_data(
    self,
    payload: bytes,
) -> list[bytes]:
    ...
```

内部：

```python
return self.send_control_command(
    cmd=0x34,
    data=payload,
    ...
)
```

---

# 18. 增加高级接口

在 telemetry 层新增：

```python
class TelemetrySender:
    def __init__(self, hid_device: Nova98Hid):
        self._hid = hid_device

    def send(self, status: TelemetryStatus) -> None:
        payload = encode_system_status(status)
        self._hid.send_temporary_data(payload)
```

职责关系必须保持：

```text
TelemetryStatus
       ↓
TelemetryEncoder
       ↓
bytes
       ↓
TelemetrySender
       ↓
Nova98Hid
```

不要出现：

```text
MetricsService
      ↓
直接 send_control_command()
```

---

# 19. 关于 cmd 52 ACK

必须严格依据真实设备行为。

当前通用：

```python
send_control_command()
```

使用：

```text
response expected command = request command
```

即：

```text
55 34 ...
```

Agent 必须先检查官方 AULA HUB 的 JS。

确认：

```text
cmd 52
```

实际是否：

```text
需要 ACK
```

以及 ACK command 是否确实为：

```text
0x34
```

如果官方代码没有等待 ACK：

不要人为增加硬性 ACK 要求。

如果官方代码有 ACK：

严格照搬。

---

# 20. 不确定协议行为时的规则

Agent 如果发现：

```text
cmd 52 framing
```

与当前 `send_control_command()` 不能完全对应，

禁止：

```text
靠猜修改协议
```

必须：

```text
回到 AULA HUB JS
↓
定位 cmd 52 调用
↓
记录真实 byte layout
↓
更新 docs/protocol.md
↓
再编码
```

---

# 21. Commit 3

提交：

```text
feat: add native telemetry HID transport
```

---

# 22. 第四阶段：建立独立实机测试命令

在 CLI 增加：

```bash
python -m nova98.cli telemetry-test
```

参数：

```text
--cpu

--cpu-temp

--gpu

--gpu-temp

--current-temp

--high-temp

--low-temp

--weather

--humidity
```

示例：

```bash
python -m nova98.cli telemetry-test \
  --cpu 42 \
  --cpu-temp 55 \
  --gpu 61 \
  --gpu-temp 64
```

---

# 23. telemetry-test 必须是单次执行

禁止：

```text
默认循环
```

默认：

```text
发送一次
退出
```

这样便于安全实验。

---

# 24. 增加 dry-run

支持：

```bash
python -m nova98.cli telemetry-test \
  --cpu 50 \
  --cpu-temp 55 \
  --dry-run
```

打印：

```text
TelemetryStatus

Encoded Payload

24-byte Hex
```

例如：

```text
00 00 00 00 00 00 5A ...
```

但不访问 HID。

---

# 25. Commit 4

提交：

```text
feat: add telemetry hardware test command
```

---

# 26. 第五阶段：第一次实机验证

这是本阶段最关键的 Gate。

任何后续 Runtime 重构必须等待这一实验结果。

---

# 27. Experiment A：单字段 CPU

首先执行：

```bash
python -m nova98.cli telemetry-test \
  --cpu 10
```

记录：

```text
屏幕是否变化：
YES / NO

变化位置：
__________

是否覆盖原自定义背景：
YES / NO

是否需要重新上传 framebuffer：
NO
```

---

然后：

```bash
python -m nova98.cli telemetry-test \
  --cpu 50
```

---

然后：

```bash
python -m nova98.cli telemetry-test \
  --cpu 90
```

观察：

```text
10
50
90
```

是否准确反映。

---

# 28. Experiment B：CPU 温度

依次：

```text
35°C

55°C

75°C
```

执行：

```bash
python -m nova98.cli telemetry-test \
  --cpu-temp 55
```

验证：

```text
数据位置
单位
范围
刷新速度
```

---

# 29. Experiment C：GPU

依次测试：

```text
GPU usage
GPU temperature
```

即使当前电脑没有 GPU 数据源，也可发送人工测试值：

```bash
python -m nova98.cli telemetry-test \
  --gpu 73 \
  --gpu-temp 68
```

验证协议通道即可。

---

# 30. Experiment D：刷新时延

编写临时实验命令：

```text
CPU:

10
20
30
40
50
60
70
80
90
```

每：

```text
1 秒
```

更新一次。

测量：

```text
send()
→
屏幕变化
```

主观和日志时间。

至少记录：

```text
是否可以稳定 1Hz

是否存在卡顿

是否丢更新

是否 HID 超时

是否屏幕闪烁
```

---

# 31. 不要立即测试高频率

禁止第一轮测试：

```text
10Hz

30Hz

60Hz
```

先使用：

```text
1 Hz
```

然后：

```text
2 Hz
```

只有确认协议行为后再决定是否更高。

对于 CPU 监控而言：

```text
1Hz
```

已经足够。

---

# 32. Experiment E：持久性测试

这是判断该通道本质的关键实验。

步骤：

```text
1. 上传已有 Dashboard 背景

2. cmd 52 设置：
   CPU=66
   Temp=55

3. 确认屏幕正确显示

4. 拔掉 USB

5. 等待 5 秒

6. 重新连接 USB

7. 不发送任何命令

8. 观察屏幕
```

记录：

```text
背景是否保留？

CPU 66 是否保留？

Temp 55 是否保留？
```

---

# 33. 预期最理想结果

如果：

```text
背景保留

Telemetry 消失
```

说明非常可能：

```text
Background
→ Flash / persistent

Telemetry
→ RAM / temporary
```

这正是我们想要的架构。

---

# 34. Experiment F：与 TFT Upload 的关系

验证：

```text
先 cmd 52
↓
再上传 framebuffer
```

Telemetry 是否：

```text
继续存在
```

再测试：

```text
先 framebuffer
↓
再 cmd 52
```

确认 overlay 层级。

最终确定：

```text
Telemetry 是覆盖层

还是会切换到系统页

还是替换 TFT 页面
```

这会直接影响 Display Engine 架构。

---

# 35. 实验结果文档

新增：

```text
docs/native-telemetry.md
```

至少记录：

```text
协议命令

Payload

ACK

刷新速度

是否写 Flash

掉电行为

与自定义背景关系

CPU 显示位置

GPU 显示位置

Temperature 显示位置

最大稳定更新频率

异常行为
```

不得只把实验结果写在 Git Commit Message。

---

# 36. Gate 1

只有以下条件全部满足：

```text
[ ] cmd 52 能被设备稳定接受

[ ] CPU Usage 可正确显示

[ ] CPU Temp 可正确显示

[ ] 多次刷新不会重新传 TFT framebuffer

[ ] 1Hz 连续更新稳定

[ ] 没有出现屏幕乱码

[ ] 没有导致设备重启

[ ] 没有破坏用户图片

[ ] 重新插拔后的行为已经明确
```

才允许进入 Runtime 重构。

---

# 37. 如果 Gate 1 失败

如果发现：

```text
cmd 52 无效果
```

不要开始做 GPU Provider。

执行：

```text
AULA HUB JS 二次逆向
```

重点找：

```text
SET_TEMPORARY_COMMAND_DATA

system status

temperature

cpu

gpu

weather
```

必要时使用：

```text
Chrome DevTools WebHID Hook
```

对比：

```text
官方 AULA HUB
```

发送系统状态时真实 Packet。

---

# 38. 第六阶段：SystemMetrics → TelemetryStatus

Gate 通过以后，增加转换层。

新增：

```python
def metrics_to_telemetry(
    metrics: SystemMetrics
) -> TelemetryStatus:
    ...
```

映射：

```text
SystemMetrics.cpu_percent
→ cpu_usage

SystemMetrics.cpu_temperature
→ cpu_temperature

SystemMetrics.gpu_percent
→ gpu_usage

SystemMetrics.gpu_temperature
→ gpu_temperature
```

转换：

```python
round()
```

并 clamp 到协议允许区间。

---

# 39. 不允许 TelemetryStatus 依赖 psutil

正确：

```text
psutil
  ↓
MetricsService
  ↓
SystemMetrics
  ↓
Mapper
  ↓
TelemetryStatus
```

错误：

```text
TelemetrySender
  ↓
psutil.cpu_percent()
```

必须保持分层。

---

# 40. 第七阶段：实现 Telemetry Scheduler

新增：

```text
nova98/scheduler/telemetry.py
```

例如：

```python
class TelemetryScheduler:

    interval_s = 1.0
```

职责：

```text
决定何时发送 Native Telemetry
```

---

# 41. Telemetry 默认刷新频率

第一版：

```text
1 second
```

配置：

```yaml
telemetry:

  enabled: true

  interval: 1.0
```

允许：

```text
0.5 秒
```

但默认不要低于：

```text
1 秒
```

---

# 42. Telemetry Change Detection

与 Static Frame 不同。

CPU 变化非常频繁，不需要设置：

```text
10%
```

这么大的阈值。

建议：

```yaml
telemetry:

  cpu_delta: 1

  gpu_delta: 1

  temperature_delta: 1
```

如果：

```text
CPU 50 → 50
```

不发送。

如果：

```text
CPU 50 → 51
```

可发送。

同时：

```text
最大 5 秒强制同步一次
```

防止某些状态不同步。

---

# 43. 第八阶段：重构 ScreenDaemon

现有：

```text
ScreenDaemon
```

同时承担：

```text
连接

静态画面刷新

异常重试
```

需要扩展为：

```text
ScreenRuntime
```

或者保留名字，但内部拆为：

```text
DeviceSession

StaticFrameController

TelemetryController
```

---

# 44. 推荐 Runtime 架构

```text
                    MetricsService
                          │
                    SystemMetrics
                          │
               ┌──────────┴──────────┐
               │                     │
               ▼                     ▼

       TelemetryController     StaticFrameController
               │                     │
               │                     │
       metrics_to_telemetry       Renderer
               │                     │
               ▼                     ▼
         TelemetryStatus          PIL Image
               │                     │
               ▼                     ▼
             cmd 52             RGB565 Buffer
               │                     │
               │                     ▼
               │                TFT uploader
               │                     │
               └──────────┬──────────┘
                          ▼

                      Nova98Hid
```

---

# 45. DeviceSession

建议将：

```text
HID connect

disconnect

reconnect

backoff
```

从业务刷新逻辑中进一步抽离。

例如：

```python
class DeviceSession:

    def ensure_connected(self) -> bool:
        ...

    @property
    def device(self) -> Nova98Hid:
        ...
```

Static 和 Telemetry 共用同一个：

```text
Nova98Hid
```

连接。

不能创建两个独立的 HID Client 抢占设备。

---

# 46. Static Frame 刷新策略

Static Frame 以后只负责：

```text
背景

主题

RAM

Network

其他无法 Native Overlay 的数据
```

默认：

```text
5 min
```

甚至：

```text
仅发生明显变化时更新
```

如果 RAM / Network 暂时还必须显示实时值，则仍可：

```text
30～60 秒
```

低频刷新。

---

# 47. Native Telemetry 刷新策略

Native：

```text
CPU
CPU Temperature
GPU
GPU Temperature
```

默认：

```text
1 秒
```

形成：

```text
FAST PATH
```

---

# 48. 最终形成 Fast / Slow Path

```text
FAST PATH
─────────────────────

Metrics 1s
   ↓
CPU/GPU/Temp
   ↓
cmd 52
   ↓
Native Overlay


SLOW PATH
─────────────────────

Metrics
   ↓
RAM/Network/Layout
   ↓
Renderer
   ↓
65056 Byte Frame
   ↓
TFT Upload
```

这是本阶段的最终软件架构目标。

---

# 49. 不再使用 Frame Hash 判断 Telemetry

当前：

```text
frame.sha256
```

只用于：

```text
Static Frame
```

Telemetry 应使用：

```text
TelemetryStatus equality
```

例如：

```python
if telemetry == previous_telemetry:
    skip()
```

---

# 50. 第九阶段：GPU Provider

只有 Telemetry 通道已经验证以后才做。

---

# 51. GPU Provider 接口

新增：

```python
class GPUProvider(Protocol):

    def get_usage(self) -> float | None:
        ...

    def get_temperature(self) -> float | None:
        ...
```

或：

```python
@dataclass
class GPUMetrics:
    usage: float | None
    temperature: float | None
```

推荐：

```python
class GPUProvider:
    def read(self) -> GPUMetrics:
        ...
```

---

# 52. GPU Provider 第一阶段范围

根据开发机器平台优先支持一个平台。

如果当前主要运行在：

```text
macOS
```

优先 macOS。

如果开发机器：

```text
NVIDIA Windows/Linux
```

优先 NVML。

不要一开始同时实现：

```text
NVIDIA
AMD
Intel
Apple
Windows
Linux
macOS
```

---

# 53. GPU Provider 的失败策略

任何读取失败：

```text
gpu_percent = None

gpu_temperature = None
```

不能导致：

```text
MetricsService crash
```

更不能导致：

```text
ScreenDaemon crash
```

---

# 54. 第十阶段：配置结构调整

最终配置建议：

```yaml
device:

  reconnect_interval: 5


metrics:

  sampling_interval: 1

  cpu: true
  memory: true
  temperature: true
  gpu: true
  network: true


telemetry:

  enabled: true

  interval: 1

  force_interval: 5

  thresholds:

    cpu: 1
    gpu: 1
    temperature: 1


static_display:

  enabled: true

  min_interval: 30

  force_interval: 300


layout:

  name: system
```

---

# 55. CLI 调整

最终应支持：

```bash
nova98-screen devices
```

---

```bash
nova98-screen metrics
```

---

```bash
nova98-screen preview
```

---

```bash
nova98-screen show
```

表示：

```text
上传一次 Static Frame
```

---

新增：

```bash
nova98-screen telemetry-test
```

---

新增：

```bash
nova98-screen telemetry
```

显示当前编码：

```text
CPU      43
CPU TEMP 55
GPU      62
GPU TEMP 64
```

---

```bash
nova98-screen run
```

最终启动：

```text
Static
+
Telemetry
```

双通道 Runtime。

---

# 56. 日志设计

Telemetry 不要每秒使用：

```text
INFO
```

否则日志大量刷屏。

建议：

```text
DEBUG:
Telemetry sent CPU=...

INFO:
Telemetry channel started

INFO:
Telemetry channel stopped

WARNING:
Telemetry send failed
```

Static Frame 保持：

```text
INFO
```

---

# 57. USB 错误处理

如果 Telemetry 发送失败：

```text
不要立即触发连续三次大 Frame Upload
```

正确行为：

```text
Telemetry Send Error
       ↓
DeviceSession disconnect
       ↓
Reconnect
       ↓
重新同步 telemetry
```

Static Frame 是否重新上传：

取决于：

```text
屏幕断开后是否仍保留背景
```

如果保留：

```text
不重新上传
```

---

# 58. 不要把 Telemetry Failure 当作 Flash Failure

必须区分：

```text
TelemetryTransportError
```

与：

```text
FrameUploadError
```

因为：

```text
cmd 52
```

理论上是低风险临时命令。

而：

```text
cmd 80 / Frame Upload
```

可能涉及 Flash。

这两者的重试策略不应完全相同。

---

# 59. 第十一阶段：测试结构

至少增加：

```text
tests/
    test_profiles.py

    test_telemetry_model.py

    test_telemetry_encoder.py

    test_telemetry_mapper.py

    test_telemetry_scheduler.py

    test_device_session.py
```

---

# 60. 硬件测试继续隔离

所有真实 HID 测试：

```python
@pytest.mark.hardware
```

普通：

```bash
pytest
```

不得向键盘写任何数据。

---

# 61. Hardware Test

允许：

```bash
pytest -m hardware
```

但即使 hardware 标记测试：

默认也不要自动：

```text
上传 framebuffer
```

Telemetry 测试可以独立：

```text
telemetry hardware test
```

---

# 62. 第十二阶段：Documentation

必须更新：

```text
README.md
```

增加架构：

```text
Native Telemetry
```

---

更新：

```text
docs/protocol.md
```

补充：

```text
cmd 52 已验证状态
```

区分：

```text
来自官方 JS

和

来自实机验证
```

---

新增：

```text
docs/native-telemetry.md
```

记录完整实验。

---

# 63. 建议新的 README 架构图

```text
                    System

                      │

                MetricsService

                      │
             ┌────────┴────────┐
             │                 │

          Fast Path         Slow Path

             │                 │

      CPU/GPU/Temp       RAM/Network/UI

             │                 │

      Native Telemetry      Renderer

             │                 │

          cmd 52          Framebuffer

             │                 │

             │             TFT Upload

             └────────┬────────┘

                      │

                   NOVA98
```

---

# 64. Commit 计划

严格推荐以下顺序。

## Commit 1

```text
fix: align NOVA98 HID interface profile semantics
```

---

## Commit 2

```text
feat: add NOVA98 native telemetry encoder
```

---

## Commit 3

```text
feat: add native telemetry HID transport
```

---

## Commit 4

```text
feat: add telemetry hardware test command
```

---

## Commit 5

实机验证后：

```text
docs: document NOVA98 native telemetry behavior
```

---

## Commit 6

```text
feat: map system metrics to native telemetry
```

---

## Commit 7

```text
feat: add native telemetry scheduler
```

---

## Commit 8

```text
refactor: split static frame and telemetry display paths
```

---

## Commit 9

```text
feat: add GPU metrics provider
```

---

## Commit 10

```text
docs: update runtime architecture for dual display channels
```

---

# 65. Agent 停止条件

出现以下任一情况，立即停止协议写操作。

---

## Stop 1

cmd 52 响应格式与官方 JS 不一致。

---

## Stop 2

屏幕出现：

```text
乱码
花屏
异常闪烁
内置菜单消失
```

---

## Stop 3

发送 cmd 52 后设备：

```text
USB disconnect
```

或重启。

---

## Stop 4

Telemetry 命令导致：

```text
用户背景图片被覆盖或损坏
```

---

## Stop 5

需要猜测未知 Flash 地址。

本阶段：

```text
绝对禁止 raw flash write
```

---

# 66. Agent 决策规则

遇到协议不确定性：

```text
代码猜测
```

优先级最低。

必须优先：

```text
官方 AULA HUB JS
      ↓
现有 docs/protocol.md
      ↓
实机最小实验
      ↓
再实现
```

---

# 67. 本阶段验收标准

本阶段完成必须满足：

```text
[ ] HID Profile 字段语义正确

[ ] Interface 2 / FF68 正确作为 Control

[ ] Interface 3 / FF67 正确作为 TFT

[ ] TelemetryStatus 数据结构完成

[ ] cmd 52 payload 编码完成

[ ] payload 具有完整测试

[ ] telemetry-test CLI 完成

[ ] CPU Usage 实机显示成功

[ ] CPU Temperature 实机显示成功

[ ] GPU 测试值实机显示成功

[ ] 1Hz 连续更新稳定

[ ] Native Telemetry 不需要重新上传 65KB Frame

[ ] 掉电行为已经验证

[ ] Telemetry 与 Static Frame 的层级关系已经验证

[ ] docs/native-telemetry.md 完成

[ ] Static / Telemetry 两条通道解耦

[ ] CPU/GPU/Temp 使用 Fast Path

[ ] Static Frame 使用 Slow Path

[ ] pytest 全部通过

[ ] 普通 pytest 不访问实际 HID
```

---

# 68. 最终预期行为

程序运行：

```bash
nova98-screen run
```

系统：

```text
MetricsService
每 1 秒采样
```

CPU：

```text
47%
↓
cmd 52
↓
NOVA98
```

CPU 温度：

```text
56°C
↓
cmd 52
↓
NOVA98
```

GPU：

```text
38%
62°C
↓
cmd 52
↓
NOVA98
```

而背景：

```text
SYSTEM
RAM
Network
Theme
```

不会随 CPU 每秒重新上传。

---

# 69. 目标运行效果

旧模式：

```text
CPU 变化
↓
生成整张图
↓
65KB
↓
16 次 HID 大块发送
↓
屏幕刷新
```

新模式：

```text
CPU 变化
↓
24 Byte Telemetry
↓
Control HID
↓
屏幕实时更新
```

这才是本阶段真正的成功标准。

---

# 70. 后续阶段，暂不执行

本阶段完成以后，下一步才考虑：

```text
Widget Engine
```

以及：

```text
Music Provider

GitHub Provider

Agent Provider

Weather Provider

Timer / Pomodoro
```

届时应基于：

```text
Display Engine
    ├ Static Layer
    └ Dynamic Layer
```

继续扩展。

不要在当前阶段提前实现。

---

# 71. Agent 当前立即执行指令

Agent 从现在开始按照以下顺序执行：

```text
Task 1
拉取并审查当前 main 分支。

Task 2
运行现有 pytest，建立测试基线。

Task 3
修复 DeviceProfile 中 Control / Display Usage Page 的语义错位。

Task 4
补充相关单元测试。

Task 5
实现 TelemetryStatus。

Task 6
实现 cmd 52 24-byte 系统状态 encoder。

Task 7
补充完整 encoder 单元测试。

Task 8
检查 AULA HUB JS 中 cmd 52 的真实发送与 ACK 行为。

Task 9
实现 send_temporary_data()。

Task 10
实现 TelemetrySender。

Task 11
实现 telemetry-test --dry-run。

Task 12
实现 telemetry-test 单次真实发送。

Task 13
停止自动开发，进入实机验证 Gate。

Task 14
完成 CPU 10/50/90 实验。

Task 15
完成 CPU Temp 实验。

Task 16
完成 GPU 人工数据实验。

Task 17
完成 1Hz 连续刷新实验。

Task 18
完成 USB 拔插持久性实验。

Task 19
完成 Telemetry / Static Frame 层级实验。

Task 20
将实验结果写入 docs/native-telemetry.md。

Task 21
若 Gate 通过，重构为 Fast Path + Slow Path。

Task 22
将 SystemMetrics 接入 Native Telemetry。

Task 23
实现 TelemetryScheduler。

Task 24
再实现 GPUProvider。

Task 25
更新 README、架构文档和测试。

Task 26
运行完整测试并进行最终代码审查。
```

---

# 72. 最重要的执行纪律

Agent 必须始终遵守：

```text
协议事实 > 推测

实机验证 > 理论设计

Native Command > 高频 Flash 写入

小步提交 > 一次大改

硬件安全 > 开发速度
```

当前阶段的技术目标不是“显示更多东西”。

而是验证并建立：

```text
NOVA98 真正的实时数据显示能力。
```