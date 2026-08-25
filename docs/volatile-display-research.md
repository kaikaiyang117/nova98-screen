# NOVA98 易失性显示通道研究报告

研究目标：确认 NOVA98 是否存在 RAM-only / 不写 SPI Flash 的实时显示通道。

结论：**截至当前逆向范围，未在 AULA HUB 实际使用的 HID 协议、已分析的
SDK 命令集和全部前端调用路径中，发现 NOVA98 可用的 RAM-only /
volatile TFT display channel。**

注意区分两个层次：
- 逆向证据 ≠ 固件层面的绝对证明（可能存在文档/前端均未覆盖的
  undocumented 命令）；
- 因此工程实现按「当前无可用易失性显示通道」处理，
  项目正式定位为 low-frequency keyboard status display。

## 研究方法

对 AULA HUB 官方前端做了穷尽式静态分析：
- 完整反混淆 vendor SDK（命令枚举 `Ut`、传输层 `An`/`Z4`/`rT`）
- 下载并扫描全部 119 个懒加载 chunk + tftScreen/route/pointScreen 页面 chunk
- 对每个 TFT 相关命令核对了定义与调用方

## 命令枚举全集与使用状态

| cmd | 名称 | 前端是否调用 | 备注 |
|---|---|---|---|
| 1 / 2 | COMMUNICATION_START/END | ❌ 死代码 | 无会话握手 |
| 52 | SET_TEMPORARY_COMMAND_DATA | ✅ 仅时钟变体 | 见下 |
| 79 | SET_FLASH_DOWNLOAD | ❌ 死代码 | |
| 80 | SET_TFT_USER_ANIMATION | ✅ 图片/GIF 上传 | 写 Flash，已验证 |
| 81 | SET_TFT_BUILT_IN_INDEX | ✅（其他型号）| NOVA98 实测 ACK 但无效果 |
| 250/253 | GET_DEVICE_NOTIFY / GET_TFT_STATE_NOTIFY | ❌ 死代码 | 监听器从未注册 |

`SET_MUSIC_DATA`(53) 是 LED 音乐频谱数据，与 TFT 屏幕无关。

## cmd 52 的真实角色（修正此前认知）

官方 HUB 在 NOVA98 的屏幕编辑页有一个手动「同步时间」按钮
（`supplement603.text2` → `timeCheck()` → `pke`），发送：

```text
cmd 52, 10 字节: 5A 01 5A <年%100> <月> <日> <时> <分> <秒> <星期(周日=0)>
```

即固件确实处理 cmd 52 的**时钟子命令**；系统状态子命令（CPU/温度，
byte[6]='Z' 布局）则是无 UI 调用方的死代码。

实机验证：时钟同步命令发送成功（ACK），但当前自绘 Dashboard 上无可见变化——
符合预期：时间覆盖层只渲染在官方编辑器设计内嵌了时钟控件的图片上。

## 最终判定

```text
NOVA98 显示通道清单：
  cmd 80  framebuffer  → SPI Flash（持久）     ✅ 唯一可用
  cmd 52  clock        → 需官方编辑器时钟控件   （不适用于自绘帧）
  cmd 52  system info  → 固件不渲染            ❌
  cmd 81  built-in page→ 固件不响应            ❌
  RAM/volatile channel → 当前协议/HUB 中未发现可用实现 ⚠️
```

因此本项目定位为 **low-frequency keyboard status display**：
所有动态数据经 cmd 80 帧上传，受 Flash 寿命约束采用低频节流刷新。
