# NOVA98 协议分析

状态：**结构比对完成，写入协议尚未验证。**

## 1. F108 Pro 已知协议（来源：parsiya/f108-pro、kitan-shiragami/aula-tft-uploader）

### 设备

| 项 | 值 |
|---|---|
| VID:PID | `0x0C45:0x800A` (SONiX) |
| Product | `AULA F108Pro` |
| 最大帧数 | 141 |

### HID 接口

| Interface | Usage Page | 用途 |
|---|---|---|
| 2 | `0xFF68` | LCD 像素数据：4096 字节 Output Report；每页 ACK 为 64 字节 Input Report `01 5A 02 00 ...`（300ms 超时，ACK 可容忍丢失） |
| 3 | `0xFF13` | 控制：64 字节 Feature Report（hidapi 需前置 `0x00` report ID） |

### 控制命令序列（Interface 3 Feature Reports）

1. **BEGIN**: `04 18`（必须读回 ACK）
2. **Image header**: `04 72 <slot> ... <page_count LE16 @ offset 8..9>`
3. **像素页**: 经 Interface 2 interrupt OUT 发送（每 4096 字节页 = 64 × 64 字节包）。
   ⚠️ 若用 SET_REPORT 控制传输发送像素会直接崩溃固件。
4. **APPLY**: `04 02`（键盘写入 SPI Flash，必须读回）

控制命令间隔 ≥ 35ms（厂商 `cmd_delaytime=35`）。

### 图像格式

- 扁平缓冲：256 字节头 + N 帧 × (240×135×2 = 64800 字节 RGB565 小端)
- 头：byte[0] = 帧数；byte[1+i] = 第 i 帧 delay（单位 2ms，钳位 1–255）；余下补 `0xFF`
- 整体按 4096 字节分页，末页用 `0xFF` 补齐
- 单帧 = 65056 字节 = 恰好 16 页
- 超过 141 帧无固件保护，会覆盖相邻 SPI Flash 内置图形资源（不可恢复）

## 2. NOVA98 实际 USB Descriptor（2026-08-25 实测）

```text
VID:PID        0x38A6:0x273B
Manufacturer   AULA
Product        AULA NOVA98
```

| Interface | Usage Page | Usage | 推断 |
|---|---|---|---|
| 0 | 0x0001 | 0x0006 | 键盘 |
| 1 | 0x000C / 0x0001 | 多个 | 消费/鼠标 |
| 2 | **0xFF68** | 0x0061 | 疑似 LCD 像素传输 |
| 3 | **0xFF67** | 0x0061 | 疑似控制通道 |

## 3. 相同点

- Interface 布局一致：4 个 HID 接口，Interface 2/3 承担 LCD + 控制角色。
- **LCD 接口 Usage Page 完全一致（`0xFF68`），且都在 Interface 2**。
- 屏幕规格预期一致：240×135 RGB565，GIF 上限 141 帧。

## 4. 不同点

- VID/PID 完全不同：`38A6:273B` vs SONiX `0C45:800A`（主控可能不是 SONiX）。
- 控制接口 Usage Page：`FF67` vs `FF13`。
- 控制命令字节序列是否相同 **未验证**。

## 5. 兼容性判断

结构上高度疑似同一方案家族（LCD 数据路径几乎可以确定沿用 FF68 中断 OUT +
ACK IN 模式），但控制通道命令集不能假定兼容。

结论：
- 可以按「F108 Pro 风格」实现 uploader 骨架与安全护栏；
- 第一次真实上传前必须先做只读/最小化探测（BEGIN + 读回 ACK），
  并由用户人工确认后才能进入 Phase 6 单帧上传。

## 6. 停止条件（触发即停止一切写入）

1. BEGIN 命令读回无响应或非预期 ACK。
2. 首个 4096 字节页出现 timeout / device reset / disconnect / unknown response。
3. 键盘出现乱码、内置菜单异常、屏幕异常 → 立即停止 Flash 写入并抓包分析。

## 参考

- https://github.com/parsiya/f108-pro (`ai-docs/hid-protocol.md`)
- https://github.com/kitan-shiragami/aula-tft-uploader (`aula_tft/protocol.py`, `transport.py`, `device.py`)
