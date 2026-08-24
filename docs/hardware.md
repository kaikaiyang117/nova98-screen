# NOVA98 Hardware Notes

## 设备信息

```text
型号：           AULA NOVA98
连接模式：       USB 有线（第一阶段唯一支持模式）
屏幕：           1.14 英寸 TFT
预期分辨率：     240 × 135
预期像素格式：   RGB565
已知 GIF 上限：  141 帧
协议状态：       尚未验证
```

## 实际 USB 枚举结果（待填入）

> 以下字段必须来自 `scripts/enumerate_hid.py` 对真实设备的输出，
> 禁止使用猜测值或 F108 Pro 的值。

实测时间：2026-08-25（macOS，hidapi 枚举）

```text
VID:             0x38A6
PID:             0x273B
Manufacturer:    AULA
Product:         AULA NOVA98
Serial:          <空>
```

## HID 接口布局（实测）

| Interface | Usage Page | Usage | 推断用途 |
|---|---|---|---|
| 0 | 0x0001 | 0x0006 | 键盘 |
| 1 | 0x000C / 0x0001 | 多个 | 消费控制 / 鼠标 / 系统控制 |
| 2 | 0xFF68 | 0x0061 | 疑似 LCD 像素传输（与 F108 Pro 相同 Usage Page） |
| 3 | 0xFF67 | 0x0061 | 疑似控制命令通道 |

注意：NOVA98 的 VID/PID 与 F108 Pro (`0C45:800A`, SONiX) 完全不同，
控制通道 Usage Page 为 `FF67` 而非 `FF13`。
但 LCD 接口的 Usage Page `FF68` 与 F108 Pro 完全一致。

## 安全基线

- 所有 probe 操作默认只读。
- 任何 USB 写操作必须显式调用 upload/test 命令。
- `import nova98` 或构造设备对象时，禁止自动发送任何 USB 数据。
- 协议验证前禁止批量上传、GIF 上传和任何原始 Flash 写操作。
- 测试阶段上传严格限制为单帧（`MAX_TEST_FRAMES = 1`）。
