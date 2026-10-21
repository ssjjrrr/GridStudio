# GridStudio 1.1.0

**简体中文** | [English](README.en.md)

适用于 **Windows、Linux 和 macOS** 的自由画布视频播放器。把多个视频放在同一张画布上，自由移动、缩放和叠放；鼠标静止时只显示视频。

[下载最新版本](https://github.com/ssjjrrr/GridStudio/releases/latest) · [1.1.0 发布页](https://github.com/ssjjrrr/GridStudio/releases/tag/v1.1.0) · [更新记录](CHANGELOG.md)

![GridStudio 实际界面：四路视频以 2×2 布局并排播放](docs/images/preview.png)

实际 Windows 便携版截图，四个画面互不覆盖。[影片来源与署名](docs/preview-sources.md)

## 主要功能

- **自由画布与图层**：拖动视频移动位置，拖动八个边缘或角点改变大小；可置顶、置底、逐层调整顺序，也可精确输入位置和尺寸。
- **按需显示的播放控件**：移动鼠标显示标题、进度、播放/暂停、静音和音量；静止约 2 秒后隐藏。拖动进度或音量时保持显示。
- **完整显示或填满**：保持原比例、等比裁切铺满、拉伸填满。自由画布的原比例留白会透出下层视频，鼠标也可穿过留白选择下层。
- **独立变换与复制**：裁剪、90° 旋转、水平/垂直镜像。复制保留来源、进度、变换、显示方式、音量、速度、循环和同步设置。
- **循环与同步**：整个视频或 A/B 区间循环；按时间、保留时间差、按播放百分比同步，支持独立的同步组。
- **工作区与网格**：保存 `.gstudio` 工作区，恢复画面位置、尺寸、层级和播放设置，同时支持自由画布与网格布局。
- **中英文界面**：默认跟随系统语言，可通过右键菜单切换并保存语言偏好；完整说明同时提供中英文。

## 下载与启动

| 系统 | 1.1.0 下载 | 启动方式 |
| --- | --- | --- |
| Windows 10 1809+ / Windows 11，x64 | [Windows x64 ZIP](https://github.com/ssjjrrr/GridStudio/releases/download/v1.1.0/GridStudio-1.1.0-Windows-x64.zip) | 完整解压，运行 `GridStudio.exe` |
| Ubuntu 22.04+，x86_64 | [Linux x64 TAR.GZ](https://github.com/ssjjrrr/GridStudio/releases/download/v1.1.0/GridStudio-1.1.0-Linux-x64.tar.gz) | 解压，运行 `GridStudio/GridStudio` |
| macOS 13+，Apple Silicon | [macOS arm64 ZIP](https://github.com/ssjjrrr/GridStudio/releases/download/v1.1.0/GridStudio-1.1.0-macOS-arm64.zip) | 解压，将 `GridStudio.app` 拖入「应用程序」后打开 |
| macOS 13+，Intel | [macOS x64 ZIP](https://github.com/ssjjrrr/GridStudio/releases/download/v1.1.0/GridStudio-1.1.0-macOS-x64.zip) | 解压，将 `GridStudio.app` 拖入「应用程序」后打开 |

[源码 ZIP](https://github.com/ssjjrrr/GridStudio/releases/download/v1.1.0/GridStudio-1.1.0-source.zip) · [SHA-256 清单](https://github.com/ssjjrrr/GridStudio/releases/download/v1.1.0/GridStudio-1.1.0-SHA256SUMS.txt) · [本版验证记录](docs/validation-1.1.0.md)

所有安装包均自带 Python 和 Qt，无需安装 Python 或 VLC。Windows 和 Linux 请保留整个解压目录，包括 `_internal`、`licenses` 和 `demo`；macOS 请保留完整的 `.app`。

Linux 需要图形桌面及 Qt 的系统图形/音频依赖，支持基线为 Ubuntu 22.04 x64；其他发行版未逐一验证。可运行随包的 `install-desktop-entry.sh` 添加当前用户的应用菜单入口。依赖与排错见[完整操作说明](README.txt)。

macOS 版本采用本地签名（ad-hoc），**没有 Apple Developer ID 签名或公证**。首次启动若提示无法验证开发者或未公证，请在确认下载来源后按 Apple 的[官方步骤](https://support.apple.com/102445)，到「系统设置 → 隐私与安全性」选择「仍要打开」。

## 开始使用

1. 将视频拖入窗口开始播放，默认静音。
2. 按 **Tab** 进入编辑状态。拖动画面内部移动位置，拖动边缘或四角缩放；按住 **Shift** 可保持画面框原有比例。
3. 右键 **图层** 调整前后顺序，或从列表选择被遮住的画面。
4. 再按 **Tab** 或 **Esc** 返回纯播放；**F11** 切换全屏。
5. 右键 **工作区 → 保存**，保存构图和播放设置。

右键 **Language / 语言** 可选择简体中文、English 或跟随系统；切换不增加常驻工具栏。也可用 `--language zh_CN` 或 `--language en` 启动。

右键 **工作区 → 打开** 可体验随包的 `demo/` 示例。Windows/Linux 示例位于程序目录；macOS 位于 `GridStudio.app/Contents/Resources/demo/`（Finder 中右键应用 → 显示包内容）。工作区记录视频路径，不嵌入视频；移动时请保留引用的视频。

视频文件自身的黑色内容仍然覆盖下层画面；可用裁剪去除文件自带黑条。网格模式和聚焦单个视频时保留正常留白。更多操作见 [README.txt](README.txt)。

## 快捷键

macOS 使用 **⌘ Command** 替代下表中的 Ctrl；部分键盘需按 Fn+F11。

| 操作 | 快捷键 |
| --- | --- |
| 编辑画布 / 返回纯播放 | Tab |
| 全屏 | F11 |
| 添加视频 / 打开工作区 / 保存工作区 | Ctrl+O / Ctrl+Shift+O / Ctrl+S |
| 复制 / 关闭当前画面 | Ctrl+D / Ctrl+W |
| 上移 / 下移一层 | Ctrl+] / Ctrl+[ |
| 置顶 / 置底 | Ctrl+Shift+] / Ctrl+Shift+[ |
| 编辑时移动 1 像素 | Shift+方向键 |
| 播放 / 暂停；静音 | 空格；M |
| 开关循环；设置 A / B 点 | L；[ / ] |
| 同步全部视频到当前画面 | Ctrl+G |
| 后退 / 前进 5 秒 | ← / → |
| 旋转；裁剪 | R；C |
| 聚焦 / 返回布局 | F 或双击 |

## 从源码运行

使用 Python 3.12.14；运行依赖固定为 `PySide6==6.10.2`。在项目根目录执行：

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Linux / macOS 终端：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

可传入视频或 `.gstudio` 工作区路径，或加 `--edit` 直接进入编辑状态。`--language en` / `--language zh_CN` 指定界面语言。

## 构建与验证

在目标平台原生构建：Windows 运行 `./build.ps1`，Linux/macOS 运行 `./build.sh`。已安装开发依赖时可直接运行 `python scripts/build.py`。本项目不将 Windows 构建产物转换为 Linux 或 macOS 应用。

安装 `requirements-dev.txt` 后，在测试进程中设置 `GRIDSTUDIO_LANGUAGE=zh_CN`，运行 `python -m pytest tests -q -o faulthandler_timeout=30`。平台依赖、两项真实悬停测试、原生构建和归档验证的完整命令见[开发说明](docs/development.md)。

[CI](.github/workflows/ci.yml) 为 Windows x64、Linux x64、macOS Apple Silicon 和 Intel 分别执行测试、构建和最终归档验证。实际执行结果见 [GitHub Actions](https://github.com/ssjjrrr/GridStudio/actions) 与[本版验证记录](docs/validation-1.1.0.md)。

## 性能与兼容范围

每个视频（含副本）独立解码，最多 64 个画面。流畅程度取决于编码、分辨率、帧率、硬件和并发数量；同步不保证硬件级逐帧锁定。Qt Multimedia 使用 FFmpeg 后端；容器和编码的兼容范围与 VLC/GridPlayer 不完全相同。裁剪、旋转和镜像只改变显示，不修改原文件。

已有优化包括增量更新图层、按需运行播放控制时钟、复用界面状态与局部绘制。在首次发布前 Windows 内部基线中，16 个合成图层的 20 次复制/删除，三轮中位耗时由 5132 ms 降至 498 ms。它衡量该场景的界面开销，**不是解码帧率、真实多路 4K 能力或本次跨平台发布的新测量**。方法与范围见[性能审计](docs/performance-audit.md)和[基准说明](benchmarks/README.txt)。

## 项目资料与许可证

基于 Python、PySide6 和 Qt Multimedia 独立实现。[GridPlayer](https://github.com/vzhd1701/gridplayer) 是多画面使用理念的参考，本项目未包含其源代码。

- [开发、测试与构建](docs/development.md) · [English](docs/development.en.md)
- [性能审计](docs/performance-audit.md) · [English](docs/performance-audit.en.md)
- [测试媒体](docs/test-media.md) · [English](docs/test-media.en.md)
- [预览影片来源与署名](docs/preview-sources.md) · [English](docs/preview-sources.en.md)
- [更新记录](CHANGELOG.md) · [English](CHANGELOG.en.md)
- 原创代码采用 [MIT 许可证](LICENSE)。第三方组件见[中文声明](THIRD_PARTY_NOTICES.txt) / [English notices](THIRD_PARTY_NOTICES.en.txt) 和 [licenses/](licenses/)；许可证原文保持不变。
