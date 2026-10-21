GridStudio 1.1.0 · 自由画布视频播放器
==================================
简体中文说明；English: README.en.txt
项目：https://github.com/ssjjrrr/GridStudio
下载：https://github.com/ssjjrrr/GridStudio/releases/tag/v1.1.0

多视频自由移动、缩放、复制与叠放；鼠标静止约 2 秒后只显示视频。
提供中文和英文界面。默认跟随系统语言，右键 Language / 语言 可选择
English、简体中文、System default / 跟随系统；菜单选择会保存。
命令行 --language en / --language zh_CN 仅覆盖当前运行的语言。

系统与启动
----------
Windows 10 1809+ / Windows 11 x64：
  完整解压 GridStudio-1.1.0-Windows-x64.zip，运行 GridStudio.exe。
  保留整个目录，包括 _internal、licenses、demo，不要单独复制 EXE。

Linux x86_64，Ubuntu 22.04+ 为支持基线：
  tar -xzf GridStudio-1.1.0-Linux-x64.tar.gz
  ./GridStudio/GridStudio
  保留完整目录与符号链接；需要图形桌面，不是终端播放器。
  程序目录中的 install-desktop-entry.sh 可添加当前用户的应用菜单入口。
  Ubuntu 22.04 如缺少图形/音频依赖，在终端运行：
    sudo apt-get update
    sudo apt-get install libegl1 libgl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-render-util0 libdbus-1-3 libasound2 libpulse0
  Ubuntu 24.04 使用 libasound2t64 替代 libasound2；其他发行版包名可能不同。
  如果原生 Wayland 会话遇到平台插件问题，可在已启用 XWayland 的桌面尝试：
    QT_QPA_PLATFORM=xcb ./GridStudio/GridStudio
  其他发行版未逐一验证，不能仅凭 x86_64 架构保证运行。

macOS 13+，Apple Silicon / Intel：
  分别下载 macOS-arm64.zip / macOS-x64.zip，解压后把 GridStudio.app 拖入「应用程序」。
  保留完整的 .app。两种架构分别构建，不是 Universal 2 应用。
  当前使用 ad-hoc 签名，没有 Apple Developer ID 签名或公证。
  若首次启动提示无法验证开发者或未公证，确认下载来源后，在「系统设置 → 隐私与安全性」选择「仍要打开」。
  Apple 官方说明：https://support.apple.com/102445

所有发行包均自带 Python、Qt 与媒体运行库，无需另装 Python 或 VLC。
SHA-256 清单与源码包在同一发布页。Linux 系统库与图形驱动仍由操作系统提供。

开始使用
--------
1. 将本地视频拖入窗口开始播放，默认静音。
2. 按 Tab 进入编辑状态：拖动画面内部移动，拖动边缘或四角缩放。
   按住 Shift 可保持画面框现有比例；右键可精确输入位置和大小。
3. 右键「图层」可置顶、置底、上移/下移一层，也可选择被遮挡的视频。
   选中视频不会自动改变层级。
4. 右键可复制、选择显示方式、裁剪、旋转、调速、设置循环和同步。
5. 再按 Tab 或 Esc 返回纯播放；F11 切换全屏。
6. 右键「工作区 → 保存」保存 .gstudio 工作区。

画面位置和尺寸按画布比例保存；改变窗口/屏幕大小时保留相对构图。
复制把新的画面稍微错开放到最上层，然后可独立移动和缩放。
「布局」可切换网格；拖动分隔线缩放网格，按 Tab 显示标题栏后拖动标题交换窗格。
窗口模式保留系统标题栏；F11 全屏时隐藏。

移动鼠标显示视频名称、进度、播放/暂停、静音和音量，静止约 2 秒后隐藏。
悬停进度条显示对应时间，点击或拖动可以定位；A/B 标记标出循环范围。
拖动进度或音量、按住按钮时保持显示，松开后重新计时。调高音量会自动取消静音。
音量和静音只影响当前视频；播放、暂停、定位和循环遵循当前同步组设置。

显示方式与变换
--------------
右键「画面 → 显示方式」可选择：
  保持原比例（完整显示）：默认。完整显示视频或裁剪区域，不变形。
  等比铺满（裁切边缘）：保持比例铺满画面框，隐藏超出边缘。
  拉伸填满（不裁切）：完整画面填满框，比例不同时会变形。
可将当前显示方式应用到所有窗格。Tab 切换编辑状态不会改变显示方式。
自由画布纯播放时没有固定分隔线、选框或缩放手柄。
保持原比例产生的留白会透出下层视频，也允许鼠标穿过选择下层；没有下层时显示背景。
视频本身的黑色像素和文件内自带黑边仍然不透明，可用裁剪去除自带黑条。
网格模式与聚焦单个视频保留普通留白。

复制保留来源、进度、显示方式、裁剪、旋转、镜像、速度、音量、播放状态、循环和同步组。
不在同步组中的副本独立播放。所有变换只改变显示，不修改原文件。
框选裁剪时拖出保留区域，松开应用，Esc 取消。

循环与同步
----------
右键「循环」控制开关或选择整个视频循环，默认循环整个视频。
按 [ 将当前进度设为 A，再移动至后面的位置按 ] 设置 B。
「设置 A/B 循环区间…」可精确输入秒数。L 临时关闭/恢复循环并保留标记；
「清除 A/B 标记」恢复完整范围。同步组内的循环设置联动。

Ctrl+G 或「同步 → 同步全部视频（按时间）」对齐到当前画面的播放秒数。
「按百分比」将不同时长的视频对齐到相同百分比，并按时长比例调整速度，使其同时结束。
「保留时间差」使用时间同步，保留已有时间差。也可只将部分视频加入同一组（1–4），
或让视频退出同步组；不同组独立控制。
同组联动播放/暂停、定位、快进/后退、速度和循环；复制会加入原同步组。
同步定期修正时间差，适合多视频比较，但不保证硬件级逐帧锁定。

工作区与示例
------------
.gstudio 保存画布/网格、每个画面位置尺寸、层级、网格分隔比例、路径和播放设置。
工作区不嵌入视频；请一同移动视频，或用「替换当前视频」重新指定路径。
Windows/Linux 的 demo 在程序目录；macOS 在 GridStudio.app/Contents/Resources/demo，
Finder 中右键应用并选择「显示包内容」可访问。
通过「工作区 → 打开」选择：
  自由画布与图层.gstudio / free-canvas-and-layers.gstudio
  叠放与悬停进度.gstudio / overlap-and-hover-controls.gstudio
  显示方式对比.gstudio / fit-modes.gstudio
  同步与区间循环.gstudio / synchronized-ab-loop.gstudio
  百分比同步.gstudio / percentage-sync.gstudio
  四画面对比.gstudio / four-video-comparison.gstudio
中英文文件名是相同内容的两套入口；保留旁边的 sample.mp4 与 sample-short.mp4。

快捷键
------
macOS 下用 Command（⌘）替代 Ctrl；部分键盘需 Fn+F11。
Tab                 编辑画布 / 返回纯播放
F11                 全屏
Ctrl+O              添加视频
Ctrl+Shift+O        打开工作区
Ctrl+S              保存工作区
Ctrl+D              复制当前画面
Ctrl+[ / ]          下移 / 上移一层
Ctrl+Shift+[ / ]    置底 / 置顶
Shift+方向键        编辑时移动 1 像素
Ctrl+W              关闭当前画面
Ctrl+Q              退出
空格 / M            播放或暂停 / 静音
L                   开启或关闭循环，保留标记
[ / ]               设置循环 A / B 点
Ctrl+G              同步全部视频到当前画面
← / →               后退 / 前进 5 秒
R / C               顺时针旋转 90° / 框选裁剪
F 或双击            聚焦当前画面 / 返回布局
Esc                 取消裁剪 / 返回布局 / 退出全屏 / 隐藏编辑界面

兼容与性能
----------
Qt Multimedia 使用 FFmpeg 后端；MP4、MKV 是容器，能否播放还取决于编码和设备，
格式覆盖范围与 VLC/GridPlayer 不完全相同。
每个画面独立解码，副本也占用额外资源，最多 64 个画面。
流畅度取决于分辨率、帧率、编码、硬件和并发数量。
INTERACTION_PERFORMANCE.txt、INTERACTION_PERFORMANCE.en.txt 与 PERFORMANCE.json
保存首次发布前的 Windows 性能记录；本次跨平台构建没有重新测量那些数字。
合成帧界面耗时不能推断真实 4K 解码性能或 Linux/macOS 性能。

从源码运行和构建
----------------
使用 Python 3.12.14，在源码目录执行。
Windows PowerShell：
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  .\.venv\Scripts\python.exe run.py
Linux/macOS：
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python run.py

安装 requirements-dev.txt 后，在测试进程中设置 GRIDSTUDIO_LANGUAGE=zh_CN，再运行：
  python -m pytest tests -q -o faulthandler_timeout=30
这里 python 指上述虚拟环境解释器。两项真实悬停测试另有环境开关；详细命令与平台依赖见
源码 docs/development.md（English: docs/development.en.md）。
原生构建：Windows ./build.ps1；Linux/macOS ./build.sh。
已安装依赖时也可 python scripts/build.py。
本地发布打包：python scripts/package_release.py --output dist/release
最终归档验证：python scripts/verify_bundle.py --archive <归档路径> --output artifacts
这些脚本不自动上传或创建 GitHub Release。

许可证
------
原创代码采用 MIT 许可证，见 LICENSE。
第三方组件见 THIRD_PARTY_NOTICES.txt / THIRD_PARTY_NOTICES.en.txt 与 licenses。
licenses/runtime-versions.json 和 FFmpeg-BUILD.txt 记录当前发行包实际运行库；
原始许可证文本未翻译或改写。参考 GridPlayer 的多画面理念，未包含其源代码。
