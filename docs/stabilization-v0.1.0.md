# v0.1.0 稳定化基线

日期：2026-08-25

```text
baseline commit: 6fb23b86d88fb03cda0b9dd4dbe3bc780f12e57c
local pytest:    76 passed (Python 3.13.9)
CI run id:       32817692979（此前 32812232620 同因失败）
CI failed step:  Install dependencies（pip install -e ".[dev]"）
actual error:    error: Multiple top-level packages discovered in a flat-layout:
                 ['nova98', 'layouts']
```

## 根因

pyproject.toml 缺少 `[tool.setuptools.packages.find]` 显式声明，
setuptools 的 flat-layout 自动发现把 `layouts/` 目录当作了 Python 包。

## 修法

按官方推荐显式声明：

```toml
[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["nova98*"]
```

不涉及 hidapi 系统库问题（错误发生在包发现阶段，早于依赖编译）。
