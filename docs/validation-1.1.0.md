# GridStudio 1.1.0 验证 / Validation

[简体中文](#中文) · [English](#english)

## 中文

1.1.0 增加 Linux、macOS 和中英文界面。各系统分别原生构建，使用 Python 3.12.14、PySide6/Qt 6.10.2 和 PyInstaller 6.20.0。

| 分发包 | 构建与验证环境 | 原生窗口后端 |
| --- | --- | --- |
| Windows x64 | GitHub Windows Server 2022 runner | Windows |
| Linux x64 | GitHub Ubuntu 22.04 runner | X11/xcb，Xvfb 虚拟显示器 |
| macOS Apple silicon | GitHub macOS 15 arm64 runner | Cocoa |
| macOS Intel | GitHub macOS 15 Intel runner | Cocoa |

发布检查包括：

- 每个平台运行完整回归，以及隔离执行的真实 H.264 悬停定位和播放/音量测试。
- 原生窗口环境检查画布移动/缩放、悬停控件与语言切换；英文和中文使用同一套播放实现。
- 在本平台构建应用、生成分发归档，再**解压归档并运行其中的程序**，检查多个工作区的有效视频帧、正时长、无媒体错误、截图与程序退出。
- 核对运行时版本、许可证文件摘要、动态库、Qt 中文标准对话框翻译及系统版本属性。
- Linux 归档保留执行权限与符号链接；macOS 解压后核对 `.app` 的 ad-hoc 签名。Mac 包没有 Developer ID 签名或 Apple 公证。

原生窗口交互测试通过 Qt 的 QWindow 测试接口投递合成鼠标事件，并在测试驱动内提供与这些事件一致的逻辑指针查询。它们检查实际 Qt 窗口的控件命中、遮罩、进入/离开、拖动和超时行为，不验证 CI 桌面的物理鼠标权限。

2026 年 10 月 22 日（UTC+8），Windows x64、Linux x64、macOS arm64 和 macOS x64 均通过上述检查，包括主回归、隔离的真实解码交互测试、原生窗口检查，以及最终归档解压后的 4 个播放场景。结果与各平台限定测试的跳过情况见 [发布前验证记录](https://github.com/ssjjrrr/GridStudio/actions/runs/39673550471)（代码提交 `918e485`）。

正式发布在补齐本验证记录后从主分支重新构建，并再次执行相同检查；对应的最终构建记录链接收录于 [1.1.0 发布说明](https://github.com/ssjjrrr/GridStudio/releases/tag/v1.1.0)。

边界：虚拟显示器和 CI 运行机不能证明所有桌面、显卡、编码、音频设备和多路 4K 负载下的表现。Linux 的原生检查覆盖 X11/xcb，不代表已验证原生 Wayland。macOS 13 是 Qt 的最低系统要求，本次原生验证机为 macOS 15。发布前已有 Windows 功能与性能测量继续保存在 [1.0.0 验证记录](validation-1.0.0.md)，没有将其重新标为其他系统的测量。

## English

Version 1.1.0 adds Linux, macOS and an English/Chinese interface. Each package is built natively with Python 3.12.14, PySide6/Qt 6.10.2 and PyInstaller 6.20.0.

| Distribution | Build and verification environment | Native window backend |
| --- | --- | --- |
| Windows x64 | GitHub Windows Server 2022 runner | Windows |
| Linux x64 | GitHub Ubuntu 22.04 runner | X11/xcb with an Xvfb virtual display |
| macOS Apple silicon | GitHub macOS 15 arm64 runner | Cocoa |
| macOS Intel | GitHub macOS 15 Intel runner | Cocoa |

Release checks cover:

- The complete regression suite on every platform, plus isolated real H.264 hover-seek and playback/audio-control tests.
- Canvas movement/resizing, hover controls and language switching with native windows. Both languages use the same playback implementation.
- Building, archiving and then **extracting and launching the actual distribution**, checking multiple workspaces for decoded frames, positive durations, no media errors, screenshots and successful exit.
- Runtime versions, license-file hashes, shared libraries, Qt's Chinese standard-dialog translations and platform version metadata.
- Preserved executable permissions and symbolic links on Linux, and verification of the extracted macOS application's ad-hoc signature. The Mac packages are not Developer ID signed or notarized by Apple.

Native interaction tests inject synthetic mouse events through Qt's QWindow test interface. The test driver supplies logical pointer queries consistent with those events. These checks exercise hit testing, masks, enter/leave events, dragging and timeouts in actual Qt windows; they do not verify physical mouse permissions on the CI desktop.

On October 22, 2026 (UTC+8), Windows x64, Linux x64, macOS arm64 and macOS x64 passed the checks above: the regression suite, isolated real-decoder interaction tests, native window checks, and four playback scenarios launched from the extracted archives. See the [pre-release validation run](https://github.com/ssjjrrr/GridStudio/actions/runs/39673550471) (code commit `918e485`) for results and platform-specific test skips.

The published packages are rebuilt from the main branch after adding this record and must pass the same checks again. The final build record is linked in the [1.1.0 release notes](https://github.com/ssjjrrr/GridStudio/releases/tag/v1.1.0).

Limits: virtual displays and CI machines do not establish behavior on every desktop, GPU, codec, audio device or multi-stream 4K workload. Native Linux checks cover X11/xcb, not native Wayland. Qt requires macOS 13 or later; these native checks run on macOS 15. Earlier Windows functional and performance evidence remains in the [1.0.0 validation record](validation-1.0.0.en.md) and is not relabeled as measurements on other platforms.
