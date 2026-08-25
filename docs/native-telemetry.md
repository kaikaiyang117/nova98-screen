# NOVA98 Native Telemetry 实验记录（cmd 52）

## 最终结论（2026-08-25，人工实机确认后）

**cmd 52 在 NOVA98 上不可用：固件返回 ACK 但屏幕没有任何渲染行为。**

证据链：
1. 协议层：24 字节 payload、`55 34` ACK、18 连发 0 错误、可与 cmd 80 交错。
2. 实机目视：`--cpu 10/50/90 --cpu-temp 40/55/70` 全部发送成功，
   屏幕无任何变化（用户确认）。
3. `SET_TFT_BUILT_IN_INDEX`(cmd 81) 按 F108 Pro 风格在 FF67 上以
   4104 字节帧发送槽位 0-5，同样 ACK 但屏幕无变化。
4. **官方 HUB 前端完整逆向**：NOVA98 的 TFT 页面（tftScreen chunk +
   全部 119 个懒加载 chunk）只实现 GIF/图片上传和时钟同步；
   `setTftScreenInfo`(cmd 52 系统状态) 没有任何 UI 调用方——
   它是 SDK 中给其他产品线预留的死代码。

补充（volatile 通道研究后修正）：cmd 52 并非完全死代码——官方 HUB 在
屏幕编辑页有手动「同步时间」按钮，走 cmd 52 时钟变体（5A 01 5A 布局）。
系统状态变体（CPU/温度）仍是无调用死代码。详见
`docs/volatile-display-research.md`。

工程决定：
- 遥测通道保留完整实现（协议正确、未来固件/其他型号可用），
  配置默认 `telemetry.enabled: false`。
- CPU / CPU 温度回归静态帧通道渲染（阈值节流保护 Flash）。
- 本文档保留全部实验数据供后续参考。

---

以下为原始实验记录。

## 协议事实（来源：AULA HUB JS `mke`，vendor.pretty.js:121712）

- cmd 52 `SET_TEMPORARY_COMMAND_DATA`，24 字节零填充 buffer，byte[6]=0x5A
- byte[12]=CPU占用 byte[13]=CPU温度(s8) byte[14]=GPU占用 byte[15]=GPU温度(s8)
  byte[16..18]=当前/最高/最低气温 byte[19]=天气(0-23) byte[20]=湿度(0-100)
- 官方校验范围：usage 0–100，温度 −127..127，weather 0–23，humidity 0–100
- 官方以 `maxRetries: 0` 发送，等待一次同命令 ACK（`55 34`，默认超时）
- 官方默认所有字段为 0（未提供即 0），本实现一致

## Experiment A：CPU 单字段 [ACK]

| 发送 | 结果 |
|---|---|
| --cpu 10 | ACK 正常 |
| --cpu 50 | ACK 正常 |
| --cpu 90 | ACK 正常 |

设备稳定接受 cmd 52，无 timeout / disconnect / reset。[VISUAL] 数值是否正确显示待确认。

## Experiment B/C：温度与 GPU 测试值 [ACK]

`--cpu-temp 55`、`--gpu 61 --gpu-temp 64`、`--gpu 73 --gpu-temp 68` 均被接受（编码层校验与官方一致）。

## Experiment D：刷新时延 [ACK]

18 次连续发送（CPU 10→90 ×2 轮）：

```text
send() 耗时 min/avg/max = 0.9 / 1.0 / 1.1 ms
错误 / 超时 / 断连 / 重启：0
```

每次发送都立即收到 ACK。1Hz 毫无压力，协议本身支持远高于 1Hz 的速率；
按文档纪律仍以 1Hz 为默认。

## Experiment F：与 TFT Upload 的层级关系 [ACK]

顺序执行，全部成功：

```text
1. 上传 framebuffer "FRAME A"      （16/16 chunk ACK）
2. cmd 52 CPU=66 TEMP=55           （55 34 ACK）
3. 上传 framebuffer "FRAME B"      （16/16 chunk ACK）
4. cmd 52 CPU=33 TEMP=45           （55 34 ACK）
```

两个通道在同一条连接上可任意交错，互不报错。[VISUAL] 最终屏幕应为
FRAME B 背景 + CPU 33 / TEMP 45 overlay——待人工确认后补记结论：
overlay 是覆盖层还是系统页切换。

## Experiment E：掉电持久性 —— 待用户配合

需要物理拔插 USB，无法远程完成。预期（依据 cmd 名称 TEMPORARY + 官方架构）：
背景保留于 Flash，Telemetry 消失于 RAM。待用户拔插后观察并补记。

## 结论与 Gate 状态

- [x] cmd 52 能被设备稳定接受（多次、双通道交错）
- [x] 编码校验与官方完全一致
- [x] 1Hz 连续更新稳定（实际可达 >500Hz，保守用 1Hz）
- [x] 无乱码/重启/断连迹象（ACK 层面）
- [x] 不触发 framebuffer 重传即可更新数据
- [ ] CPU/GPU/Temp 显示位置与数值正确性 [VISUAL]
- [ ] 掉电行为 [需拔插]

Gate 判定：**条件性通过（仅协议层）**。cmd 52 的 payload 布局、ACK、
发送稳定性均为程序化验证事实；但以下内容在人工实机确认前**不得视为事实**：

- CPU/GPU/温度数值是否真实显示、显示位置
- cmd 52 是 overlay 覆盖层还是切换到系统监控页
- 掉电后遥测是否消失（Experiment E 待拔插）
- 自定义背景是否被覆盖

Runtime 双通道重构已按此假设推进；若晨间目视发现 cmd 52 实际切换页面
而非 overlay，Static Renderer 需要重新评估是否恢复绘制 CPU/温度。
