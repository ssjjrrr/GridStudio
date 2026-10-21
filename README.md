# GridStudio 1.0.0

适用于 Windows 的自由画布视频播放器。把多个视频放在同一张画布上，自由移动、缩放和叠放；鼠标静止时只显示视频。

[下载最新版本](https://github.com/ssjjrrr/GridStudio/releases/latest) · [v1.0.0 发布页](https://github.com/ssjjrrr/GridStudio/releases/tag/v1.0.0) · [项目仓库](https://github.com/ssjjrrr/GridStudio)

基于 Python、PySide6 和 Qt Multimedia 独立实现。[GridPlayer](https://github.com/vzhd1701/gridplayer) 是多画面使用理念的参考，本项目未包含其源代码。

![GridStudio 1.0.0 实际界面：四路视频以 2×2 布局并排播放](docs/images/preview.png)

实际 1.0.0 Windows 便携版多视频并排画面。[预览素材来源与署名](docs/preview-sources.md) · [本机验证记录](docs/validation-1.0.0.md)

## 发布前性能优化

新增、复制和删除画面改为增量更新，保留已有视频的窗口与播放器；独立整段循环和全部暂停时不再执行每 20 毫秒的控制轮询，同步与 A/B 循环仍保留原来的检查间隔。隐藏的播放控件只记录新数据，重新显示时再刷新界面。

在发布前内部基线对照中，16 个合成视频图层、20 次复制后删除的原生 Windows 受控基准，三轮中位耗时由 5132 ms 降至 498 ms（减少 90.3%）。这里沿用发布前测量记录，未因正式版本改名重新测量；结果衡量图层管理与界面开销，**不代表解码帧率或多路 4K 播放能力**。审计范围、已实现优化和保持不变的行为见 [性能审计](docs/performance-audit.md)。

## 主要功能

- **自由画布与图层**：拖动视频移动位置，拖动八个边缘或角点改变大小；可置顶、置底、逐层调整顺序，也可精确输入位置和尺寸。
- **按需显示的播放控件**：移动鼠标显示标题、进度、播放/暂停、静音和音量；静止约 2 秒后隐藏。拖动进度或音量时保持显示。
- **完整显示或填满**：保持原比例、等比裁切铺满、拉伸填满。自由画布的原比例留白会透出下层视频，鼠标也可穿过留白选择下层。
- **独立变换与复制**：裁剪、90° 旋转、水平/垂直镜像。复制保留视频来源、进度、变换、显示方式、音量、速度、循环和同步设置。
- **循环与同步**：整个视频或 A/B 区间循环；按时间、保留时间差、按播放百分比同步，支持独立的同步组。
- **工作区与网格**：保存 `.gstudio` 工作区，恢复画面位置、尺寸、层级和播放设置，同时支持自由画布与网格布局。

每个视频（含副本）独立解码，最多 64 个画面。流畅程度取决于视频编码、分辨率、帧率、硬件和并发数量；同步不保证硬件级逐帧锁定。

## Windows 便携版

适用 Windows 10 1809 或更高版本、Windows 11，64 位。

**v1.0.0 首次正式版下载**：[Windows x64 便携版](https://github.com/ssjjrrr/GridStudio/releases/download/v1.0.0/GridStudio-1.0.0-Windows-x64.zip) · [源码包](https://github.com/ssjjrrr/GridStudio/releases/download/v1.0.0/GridStudio-1.0.0-source.zip) · [SHA-256 清单](https://github.com/ssjjrrr/GridStudio/releases/download/v1.0.0/GridStudio-1.0.0-SHA256SUMS.txt)

取得便携压缩包后，**完整解压**并运行 `GridStudio.exe`。请保留同目录的 `_internal`、`licenses` 和 `demo`，不要单独复制 EXE。便携版无需安装 Python 或 VLC。

1. 将视频拖入窗口开始播放，默认静音。
2. 按 **Tab** 进入编辑状态。拖动画面内部移动位置，拖动边缘/四角缩放；按住 **Shift** 可保持画面框原有比例。
3. 右键 **图层** 调整前后顺序，或从列表选择被遮住的画面。
4. 再按 **Tab** 或 **Esc** 返回纯播放；**F11** 切换全屏。
5. 右键 **工作区 → 保存**，保存本次构图和播放设置。

右键 **工作区 → 打开** 可体验 `demo/自由画布与图层.gstudio` 或 `demo/叠放与悬停进度.gstudio`。工作区记录视频路径，不嵌入视频；移动工作区时请同时保留其引用的视频。

视频文件自身的黑色内容仍然覆盖下层画面。网格模式和聚焦单个视频时保留正常留白。完整操作说明见 [README.txt](README.txt)。

## 从源码运行

开发和 CI 使用 **Windows x64、Python 3.12.14**。运行依赖固定为 `PySide6==6.10.2`。以下命令在项目根目录的 PowerShell 中执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

也可以传入本地视频或工作区，或直接进入编辑状态：

```powershell
.\.venv\Scripts\python.exe run.py demo\自由画布与图层.gstudio
.\.venv\Scripts\python.exe run.py --edit
```

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q -o faulthandler_timeout=30
```

测试包含真实 H.264 解码、播放定位、循环同步、像素合成、鼠标交互、窗格生命周期和独立子进程死锁回归。两项真实悬停控件检查默认需设置环境开关；CI 分开执行以便定位失败，见 [测试说明](docs/development.md#运行测试)。

```powershell
.\build.ps1
```

构建脚本在项目内建立 `.venv`，安装固定运行依赖和 `PyInstaller==6.20.0`，输出完整的 `dist/GridStudio/`，附带 `CHANGELOG.md`、`INTERACTION_PERFORMANCE.txt` 与 `PERFORMANCE.json`。使用自定义 Python 时可运行 `./build.ps1 -Python <python可执行文件路径>`。Windows 便携版应分发整个输出目录。

完成验证后，可在本地生成便携版压缩包、源码包和 SHA-256 清单：

```powershell
.\.venv\Scripts\python.exe scripts\package_release.py --bundle dist\GridStudio --output dist\release
```

打包脚本只生成本地文件，不联系 GitHub；细节见 [构建与打包说明](docs/development.md#生成本地发布包)。

[CI 工作流](.github/workflows/ci.yml) 在 Windows、Python 3.12.14 上执行测试、分别运行两个真实悬停检查，再构建和验证打包程序。实际运行状态见 [GitHub Actions](https://github.com/ssjjrrr/GridStudio/actions)；本机验证记录不代表远程 CI 已通过。CI 产物用于验证，不会自动创建 GitHub Release。

## 快捷键

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

## 性能与已知边界

交互基准、测量范围及复现方法见 [benchmarks/README.txt](benchmarks/README.txt)，发布前内部基线的三轮样本与控制查询计数保存在 [performance.json](benchmarks/performance.json)。合成帧的界面耗时不能代表真实 4K 多路解码能力，也不能代替显示器呈现延迟测量。

Qt Multimedia 使用 FFmpeg 后端；MP4、MKV 等容器能否播放仍取决于内部编码和设备，兼容范围与 VLC/GridPlayer 不完全相同。裁剪、旋转和镜像只改变显示，不修改原视频。

## 项目资料与许可证

- [开发、测试与构建说明](docs/development.md)
- [发布前性能审计](docs/performance-audit.md)
- [测试媒体来源与复现](docs/test-media.md)
- [首页预览影片的来源、许可与署名](docs/preview-sources.md)
- [更新记录](CHANGELOG.md)
- 原创应用代码采用 [MIT 许可证](LICENSE)。第三方运行库保留其各自许可证，见 [第三方声明](THIRD_PARTY_NOTICES.txt) 和 [许可证来源清单](licenses/SOURCES.json)。
