# NOVA98 协议文档（已验证）

来源：AULA HUB 官方 WebHID 配置器 JS 逆向（hub.aulacn.com），
2026-08-25 提取并整理。**此为官方驱动实际使用的协议，非推断。**

## 1. 设备

```text
VID:PID   0x38A6:0x273B（另有有线变体 0x275D）
VID 0x38A6 为 AULA 新一代非 SONiX 产品线专用
```

## 2. HID 接口角色（与 F108 Pro 相反！）

| Interface | Usage Page | 角色 |
|---|---|---|
| 0 | 0x0001 | 键盘 |
| 1 | 0x000C/0x0001 | 消费/鼠标 |
| **2** | **0xFF68** | 控制命令通道（0xAA 帧格式，32 字节 report） |
| **3** | **0xFF67** | TFT 图像流（4104 字节 output report） |

Report ID 统一为 0。hidapi 发送时前置 `0x00`。

## 3. TFT 图像上传（唯一必需的序列）

**没有 BEGIN/APPLY 握手。** 全部数据通过一条分块命令发送：

每个 wire report（4104 字节）：

| Offset | 内容 |
|---|---|
| 0 | `0xAA` |
| 1 | `0x50` (SET_TFT_USER_ANIMATION) |
| 2-3 | 分块序号 LE16，从 0 开始 |
| 4-5 | 总块数 LE16 |
| 6-7 | 常量 `0x50 0x06`（源码字面量 `6619136/4096`） |
| 8..4103 | 4096 字节 payload |

payload 流 = 256 字节头 + N 帧 × RGB565 小端像素：

- 头 `[0]` = 帧数；`[1+i]` = 第 i 帧 delay×5；最后一帧 delay 槽强制 0；其余 `0xFF`
- RGB565：`(r>>3)<<11 | (g>>2)<<5 | b>>3`，小端
- 单帧 = 256 + 64800 = 65056 字节 → 16 块，末块补 `\x00`

每块 ACK：input report，`byte[0]=0x55, byte[1]=0x41`（SET_LED_USER_ANIMATION），
超时 2000ms，重试 3 次。发完最后一块后固件自动开始播放/显示。

## 4. 控制命令帧格式（Interface 2 / FF68）

32 字节 report：`AA <cmd> <len> <addr LE16> r r <last=1> r <data...>`
响应为 input report：`55 <cmd> ... <data@8:>`，按 cmd 匹配，超时 500ms。

关键命令：

| cmd | 名称 | 说明 |
|---|---|---|
| 16 | GET_DEVICE_INFO | 偏移 22-23 = tftMaxFrames（可用帧数 = 值−1，fallback 140） |
| 52 | SET_TEMPORARY_COMMAND_DATA | 子命令：时钟同步（`5A 01 5A` + 年月日时分秒星期）、**系统状态覆盖层** |
| 80 | SET_TFT_USER_ANIMATION | 图像流（见上） |
| 81 | SET_TFT_BUILT_IN_INDEX | 切换内置动画槽位 |

### cmd 52 系统状态覆盖层（重要！）

24 字节 buffer：byte[6]='Z'(90)，然后：
`byte[12]=CPU占用 byte[13]=CPU温度(s8) byte[14]=GPU占用 byte[15]=GPU温度(s8)
byte[16]=当前温度 byte[17]=最高温 byte[18]=最低温 byte[19]=天气 byte[20]=湿度`

→ 固件原生支持系统监控数据显示，第二阶段可直接利用。

**实机验证状态（2026-08-25）：**
- 来源区分：以上布局/校验范围来自官方 JS（`mke`，温度 −127..127、天气 0..23）。
- 实机确认：cmd 52 被设备稳定接受（`55 34` ACK，18 连发 0 错误，
  `send()` 平均 1ms）；可与 cmd 80 帧上传任意交错（详见
  `docs/native-telemetry.md`）。屏幕数值显示位置待人工目视最终确认。

## 5. 与 F108 Pro 的对比结论

完全不同的协议家族。F108 Pro 的 BEGIN/HEADER/APPLY、FF13/FF68 角色分配、
0xFF 页填充均不适用于 NOVA98。（此前按 F108 Pro 风格发送的探测命令
未造成任何影响——屏幕无变化即证明。）

## 参考

- AULA HUB: https://hub.aulacn.com （WebHID，Chrome/Edge）
- 方法论参考：https://github.com/sgtflixy/AulaControl
