# 开发、测试与构建

**简体中文** | [English](development.en.md)

在目标操作系统上构建并验证。开发依赖固定为 Python 3.12.14、PySide6/Qt 6.10.2，pytest 与 PyInstaller 的版本见 `requirements-dev.txt`。CI 目标为 Windows x64、Ubuntu 22.04 x64、macOS Apple Silicon 和 Intel。版本支持范围依据 [Qt 6.10 平台说明](https://doc.qt.io/qt-6.10/supported-platforms.html)；CI 的实际结果见 [Actions](https://github.com/ssjjrrr/GridStudio/actions) 和[本版验证记录](validation-1.1.0.md)。

## 建立环境

在项目根目录执行。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe run.py
```

Linux / macOS 终端：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python run.py
```

只运行应用时安装 `requirements.txt` 即可。下文的 `python` 指当前虚拟环境的解释器；Windows 可替换为 `.\.venv\Scripts\python.exe`，Linux/macOS 可替换为 `.venv/bin/python`。macOS 应使用与目标包相同架构的 Python；Apple Silicon 与 Intel 分别构建，当前没有 Universal 2 合并包。

Linux 需要图形桌面和系统图形/音频库；无桌面的 CI 还需 Xvfb。Ubuntu 常见依赖安装命令：

```sh
sudo apt-get update
sudo apt-get install libegl1 libgl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-render-util0 libdbus-1-3 libasound2 libpulse0
```

这些包适用于 Ubuntu 22.04；其他发行版的包名可能不同。更多依赖见 [Qt X11 要求](https://doc.qt.io/qt-6.10/linux-requirements.html)。Ubuntu 24.04 的 ALSA 包名为 `libasound2t64`；安装时以发行版实际包名为准。

## 运行测试

Windows PowerShell：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_MEDIA_BACKEND = 'ffmpeg'
$env:GRIDSTUDIO_LANGUAGE = 'zh_CN'
.\.venv\Scripts\python.exe -m pytest tests -q -o faulthandler_timeout=30
```

Linux / macOS：

```sh
QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg GRIDSTUDIO_LANGUAGE=zh_CN .venv/bin/python -m pytest tests -q -o faulthandler_timeout=30
```

测试命令设置 `GRIDSTUDIO_LANGUAGE=zh_CN`，因为通用界面回归会断言中文标签；专门的语言测试另行覆盖中英文。该设置只覆盖测试进程，不更改应用保存的语言偏好。

测试需要版本控制中的 `tests/fixtures/sample.mp4` 与 `sample-short.mp4`，无需安装 FFmpeg 命令行工具。[测试媒体说明](test-media.md)记录其来源与生成方法。

主套件覆盖模型、真实播放/定位/复制、循环同步、合成像素、编辑手势、透明留白、悬停控件、播放器释放及语言切换。下面两项真实悬停测试通过环境开关启用，CI 分别运行以隔离失败。Windows：

```powershell
$env:GRIDSTUDIO_REAL_HOVER_SEEK = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_hover_controls.py::test_real_video_hover_seek_updates_paused_decoder_frame -q -o faulthandler_timeout=30
Remove-Item Env:GRIDSTUDIO_REAL_HOVER_SEEK
$env:GRIDSTUDIO_REAL_HOVER_TRANSPORT = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_hover_transport.py::test_real_media_buttons_play_pause_and_volume_update_audio -q -o faulthandler_timeout=30
Remove-Item Env:GRIDSTUDIO_REAL_HOVER_TRANSPORT
```

Linux / macOS（以下每行只为该次运行设置环境变量）：

```sh
QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg GRIDSTUDIO_LANGUAGE=zh_CN GRIDSTUDIO_REAL_HOVER_SEEK=1 .venv/bin/python -m pytest tests/test_hover_controls.py::test_real_video_hover_seek_updates_paused_decoder_frame -q -o faulthandler_timeout=30
QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg GRIDSTUDIO_LANGUAGE=zh_CN GRIDSTUDIO_REAL_HOVER_TRANSPORT=1 .venv/bin/python -m pytest tests/test_hover_transport.py::test_real_media_buttons_play_pause_and_volume_update_audio -q -o faulthandler_timeout=30
```

也可同时设置两个开关后执行整个套件。每个命令必须以退出码 0 结束。`faulthandler_timeout` 等待超过 30 秒时打印线程栈，但不停止测试；CI 另有步骤/job 上限，原生死锁回归另有子进程上限。

### 多路媒体测试的等待与超时诊断

测试和基准统一使用 [`scripts/qt_test_support.py`](../scripts/qt_test_support.py) 的等待辅助，继续处理 Qt 事件及 `DeferredDelete`。不要直接使用 PySide6 6.10.2 的 `QTest.qWait` 驱动多路媒体：该绑定持有 GIL，处理延迟删除时可能与音频渲染线程的 QObject 连接锁形成互等。辅助代码使用释放 GIL 的 `QCoreApplication.processEvents(flags, int)` 和 `sendPostedEvents`，保留真实的对象销毁流程；这两个接口在[官方 6.10.2 类型系统](https://github.com/pyside/pyside-setup/blob/v6.10.2/sources/pyside6/PySide6/QtCore/typesystem_core_common.xml#L2777)中均标记为 `allow-thread="yes"`。

[诊断运行 39676275048](https://github.com/ssjjrrr/GridStudio/actions/runs/39676275048) 的 macOS 原生线程样本显示：主线程从 `QTest.qWait` 处理延迟删除，进入 `QPropertyAnimation` / `QObject` 析构后等待互斥锁；`AudioRenderer` 线程在另一条 `QObject` 析构路径上，经 `QAudioOutputWrapper.disconnectNotify` 等待 `PyGILState_Ensure`。样本支持上述 GIL 与连接锁互等的诊断，但没有标识两个析构路径为同一个 QObject 实例。

CI 的 [`scripts/run_diagnostics.py`](../scripts/run_diagnostics.py) watchdog 在无输出或总时长超限时保存日志，并在 macOS 捕获原生线程 sample，随后以退出码 124 报失败。macOS ARM 另配置同一同步、复制与删除回归各运行 **50 次 offscreen、50 次 Cocoa**；这里记录检查配置，是否通过以对应 Actions 日志为准。

### 原生定位死锁回归

```sh
python -m pytest tests/test_seek_deadlock.py -q -o faulthandler_timeout=30
```

子进程打开真实视频，建立受控的 Qt 连接锁竞争窗口，再通过媒体命令定位并检查解码帧。父进程设有 10 秒上限。它验证构造出的锁顺序，不代表重现所有间歇性卡死；常规 CI 只运行 `fixed` 模式。

## 原生构建

Windows：

```powershell
.\build.ps1
```

Linux / macOS：

```sh
./build.sh
```

脚本建立或复用 `.venv`，安装固定版本的依赖与 PyInstaller，再调用 `scripts/build.py`。Windows 可用 `./build.ps1 -Python <解释器路径>`；Unix 可用 `PYTHON=/path/to/python3 ./build.sh`。如果 `.venv` 已存在，先确认其解释器版本和架构符合目标。开发依赖已装好时，可直接执行：

```sh
python scripts/build.py
```

Windows/Linux 输出 `dist/GridStudio/`；macOS 输出 `dist/GridStudio.app`。文档、演示和许可证在 Windows/Linux 的程序目录，macOS 的 `Contents/Resources/`。应用版本来自 `gridstudio.__version__`；Windows EXE 文件/产品版本与 macOS bundle 版本必须一致。

包内包括中英文说明、更新记录、第三方声明、`licenses/`、`demo/`、性能材料与验证记录。`licenses/runtime-versions.json` 与 `licenses/FFmpeg-BUILD.txt` 记录该构建实际检查到的运行库，而非复制其他平台的版本结论；许可证摘要见 `licenses/SOURCES.json`。源码树中的 FFmpeg 配置保留原有 Windows 记录作为参考。

Windows 需要分发整个目录，不能只复制 EXE；Linux TAR.GZ 保留可执行权限与符号链接。macOS `.app` 采用 ad-hoc 签名，当前未提供 Developer ID 签名或 Apple 公证。

## 生成本地发布包

完成测试与原生构建后执行：

```sh
python scripts/package_release.py --output dist/release
```

脚本根据当前系统和架构选择构建产物，版本来自 `gridstudio.__version__`。生成对应的 `GridStudio-<版本>-Windows-x64.zip`、`-Linux-x64.tar.gz`、`-macOS-arm64.zip` 或 `-macOS-x64.zip`，以及源码 ZIP 和 SHA-256 清单。`--skip-source` 可跳过源码包，供多平台汇总发布时避免重复。

源码包只包含指定的源码、文档、工作流、测试、示例与许可证，不包含虚拟环境、Git 元数据或构建缓存。Mac ZIP 使用 `ditto` 保留应用包结构。打包命令只生成本地文件，不联系 GitHub，也不创建 Release。

## 验证最终归档

在与归档平台/架构相同的环境运行，例如：

```sh
python scripts/verify_bundle.py --archive dist/release/GridStudio-1.1.0-Linux-x64.tar.gz --output artifacts
```

Windows/macOS 将 `--archive` 改为对应 ZIP 路径。若继续使用测试时的 PowerShell 窗口，请先清除测试用环境变量，让验证器选择原生窗口后端，也让后续启动继续使用用户语言偏好：

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:GRIDSTUDIO_LANGUAGE -ErrorAction SilentlyContinue
```

Linux/macOS 上面的测试命令仅对该次运行设置环境变量；若曾自行导出 `QT_QPA_PLATFORM`，请在验证前取消它，或明确设为 Linux 的 `xcb` / macOS 的 `cocoa`。验证器重新解压最终归档，检查文件、运行库与许可材料，再启动归档中的实际程序输出 PNG 截图及 JSON 解码诊断。完整目录能启动不能替代此检查：归档时也可能丢失符号链接、执行权限或 `.app` 结构。

图形启动检查需要可用桌面：Windows 使用原生窗口，macOS 使用 Cocoa；Linux 无显示器的 CI 在 Xvfb 提供的 X11 显示中运行。正常桌面上还应目视检查画面、悬停操作、拖动和全屏。媒体测试负责进一步验证定位、循环及同步语义。

## CI

[工作流](../.github/workflows/ci.yml)在 push、pull request 或手动触发时运行，分别使用 `windows-2022`、`ubuntu-22.04`、`macos-15`（Apple Silicon）和 `macos-15-intel`。以实际工作流文件为 runner 和步骤的依据。

各平台安装依赖、执行测试和真实悬停检查、原生构建、打包，再验证最终归档中的程序。结果与归档作为 Actions artifacts 留存。CI 本身不自动创建 GitHub Release。

完整回归使用 `offscreen`；两项隔离的真实悬停测试和原生交互检查使用 Windows、Cocoa 或 X11/xcb（Linux 由 Xvfb 提供显示器）。这使实际视频定位和播放控件也覆盖系统窗口后端。

CI 使用固定提交的 `astral-sh/setup-uv` 与固定 uv 版本获取 Python 3.12.14 standalone 构建，并核对解释器版本。Python 3.12.14 属于仅源码发布的安全维护版本，不能假设 `actions/setup-python` 在所有平台都提供它；后续步骤统一使用 `.venv`。

上游资料：[Python 3.12.14](https://www.python.org/downloads/release/python-31214/) · [setup-uv](https://github.com/astral-sh/setup-uv) · [uv GitHub Actions 指南](https://docs.astral.sh/uv/guides/integration/github/)

## 性能测量

保留的历史数据是在 Windows 原生 Qt 平台上测量的。以下 PowerShell 示例只复现当前实现：

```powershell
.\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --output artifacts\interaction-current.json
.\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --media demo\sample.mp4 --output artifacts\interaction-real.json
.\.venv\Scripts\python.exe benchmarks\workspace_bench.py --platform windows --panes 16 --cycles 20 --output artifacts\workspace-current.json
```

重跑发布前内部基线对照需要另行提供当时的源码快照：

```powershell
$baselineProject = Read-Host '内部基线源码根目录'
.\.venv\Scripts\python.exe benchmarks\playback_query_bench.py --baseline $baselineProject --output artifacts\playback-query-comparison.json
```

逐个运行，每个实现至少三轮，在相同机器、缩放、窗口与输入下比较中位数。耗时不是 CI 稳定阈值、解码 FPS 或输入到显示延迟。跨平台构建没有重新测量这些历史数字；Linux/macOS 的性能不可由 Windows 结果推断。详见[性能审计](performance-audit.md)、[基准说明](../benchmarks/README.txt)与[结构化数据](../benchmarks/performance.json)。
