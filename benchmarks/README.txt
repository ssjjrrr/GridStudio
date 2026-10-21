GridStudio 性能测量
==================
简体中文；English: README.en.txt

本目录保留 1.0.0 正式发布前的既有实测。图层管理与播放控制的发布前候选使用
与正式版相同的相关实现；后续版本沿用这些记录，没有为跨平台发布重新运行基准；Linux/macOS 性能未由此测量。
原始测量数值和实测源码哈希均保留。下文的早期实现、内部基线与发布前候选
用于区分内部源码快照，不代表公开发布版本。

图层管理与控制工作：内部基线 → 发布前候选
-----------------------------------------
环境：Windows 11 x64、Qt/PySide6 6.10.2、1280×720 逻辑像素窗口、125% 缩放。
采用 Windows 原生 Qt 平台，内部基线与发布前候选顺序运行，各三轮；下面耗时取中位数。
结构化样本、计数和源文件摘要见源码中的 benchmarks\performance.json，
发行包另附 PERFORMANCE.json；macOS 位于应用包 Contents/Resources。

场景 / 指标                              内部基线 → 发布前候选
16 图层，20 次复制后删除的总耗时          5132.2 → 497.9 ms（减少 90.3%）
上述操作中已有图层的 ParentChange        1280 → 0 次
上述操作中已有图层的 Hide / Show         各 640 → 各 0 次
同一画面重复选择 1000 次的总耗时         10.00 → 1.25 ms
300 ms 普通整段循环空闲观察的时钟唤醒    13/13/15 → 0/0/0 次（三轮）

图层操作使用 16 个 640×360 合成帧，排除解码器启动与真实解码开销。
计时包含正常的事件与绘制队列处理，计时内不逐次截图；已有画面、播放器及其位置保留。
空闲观察使用合成输入和时长替身，只计控制器唤醒，不是整机 CPU 或功耗测量。

继续使用四层 3840×2160 合成帧，分别执行 120 次画布移动 / 缩放：
  移动总耗时中位数：165.5 → 155.4 ms。
  缩放总耗时中位数：235.7 → 224.7 ms。
最终位置与尺寸一致。这两个小差值与轮次波动相当，不作为显著加速承诺。
上述全部合成帧数字都不是 4K 解码性能、播放 FPS、显示器呈现延迟或最大并发数。

播放控制的确定性计数（使用 Python 替身播放器，无真实解码）：
  64 路独立整段循环，手动 50 轮检查：查询 3200 → 0 次。
  8 路已暂停百分比组，手动 50 轮检查：查询 2950 → 0 次。
  8 路播放中百分比组，手动 50 轮检查：查询 4000 → 1550 次（减少 61.3%）。
  8 路播放中百分比 A/B 组，同样检查：查询 4400 → 1550 次。
  加入 8 路百分比组：状态应用 24 → 8 次，即每个画面 3 → 1 次。
50 轮代表原 20 ms 周期下一秒的工作次数，并非实际等待一秒的 CPU 采样。
普通独立播放、原生整段循环与全部暂停时停止控制时钟；播放中的 A/B / 同步仍每 20 ms 检查。

测量当前实现（在源码目录 PowerShell 中执行，先安装 requirements-dev.txt）：
  .\.venv\Scripts\python.exe benchmarks\workspace_bench.py --platform windows --panes 16 --cycles 20 --output artifacts\workspace-current.json
  .\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --source-width 3840 --source-height 2160 --output artifacts\interaction-4k-current.json

严格复现历史对照需要当时保存的内部基线源码快照，由结果中的原始哈希标识；
当前源码只能测量当前实现，不能重建历史基线。快照根目录应包含 gridstudio\playback.py：
  $baselineProject = Read-Host '输入内部基线源码根目录'
  .\.venv\Scripts\python.exe benchmarks\workspace_bench.py --project $baselineProject --platform windows --panes 16 --cycles 20 --output artifacts\workspace-before.json
  .\.venv\Scripts\python.exe benchmarks\playback_query_bench.py --baseline $baselineProject --output artifacts\playback-query-comparison.json
  interaction_bench.py 同样支持 --project $baselineProject。

耗时场景应逐个、每份实现至少运行三轮，换用不同 --output 文件名保存样本再比较中位数；
保持机器、缩放、窗口与输入一致，避免同时运行媒体测试或其他基准。
更完整的审计范围与未更改行为见 docs\performance-audit.md。


较早一轮：画布移动 / 缩放（早期实现 → 内部基线）
------------------------------------------------
以下保留发布前较早一轮的原始结果；它们与上文的发布前候选对比样本不同，
请勿合并加速百分比，也不要视为本次正式发布时重新测量的结果。
环境：本机 Windows 11 x64、Qt/PySide6 6.10.2、1280×720 逻辑像素窗口、125% 缩放。
四层独立视频，最上层执行真实画布鼠标事件。每阶段连续 120 次移动或缩放，
每次处理正常的 Qt 更新队列；计时内不逐帧截图，不主动强制重绘整个窗口。
两份实现使用相同的 cProfile 与事件计数器。以下为该受控场景的一轮测量，单位毫秒。

输入                       移动：早期 → 基线       缩放：早期 → 基线
640×360 合成视频帧          250.3 → 118.0 (-52.8%)   335.5 → 192.8 (-42.5%)
3840×2160 合成视频帧        324.3 → 141.5 (-56.4%)   413.2 → 196.2 (-52.5%)
640×360 H.264/AAC 真实播放  354.6 → 142.2 (-59.9%)   556.3 → 224.4 (-59.7%)

合成帧用于隔离界面和绘制开销，不包含解码；不能作为四路 4K 解码性能证明。
真实播放场景在操作前后检查全部四路有效视频帧及时间戳前进，无播放器错误。
真实场景随墙钟持续播放，Qt 还会投递原生鼠标事件：本轮早期实现缩放实际进入拖动回调
172 次，内部基线 121 次。因此约 60% 只代表本轮总体耗时，严格归因采用合成帧的 43%–56%。
所有场景的最终画面位置与尺寸在两份实现中一致。
这些数字衡量事件处理和 Qt 绘制吞吐量，不是显示器呈现延迟、播放帧率或最大并发数。

主要变化：
选框只使新旧边缘失效，避免每次移动都重绘整块画布；重复像素坐标不再触发刷新。
鼠标移动只重置隐藏计时，状态未变化时复用标题、按钮状态和控件布局。
缩放不再反复刷新隐藏的网格标题，也不重复提交相同视频拟合变换。
保留原有显示质量、实时视频播放、透明留白和同步控制方式。

合成帧场景中选框累计绘制区域减少 85.7%（移动）和 79.6%（缩放）；
视频累计绘制区域减少 69.9% 和 58.8%；缩放时传输控件布局调用 990 → 100。
结构化结果及测量源文件哈希见源码中的 benchmarks\interaction-comparison.json。

复现（源码包安装依赖后，在源码目录执行）：
  python benchmarks\interaction_bench.py --platform windows --output interaction.json
  python benchmarks\interaction_bench.py --platform windows --source-width 3840 --source-height 2160 --output interaction-4k.json
  python benchmarks\interaction_bench.py --platform windows --media demo\sample.mp4 --output interaction-real.json
  --project 可指定保存的内部源码快照目录；应逐个运行，以免测试之间争抢资源。
  --screenshot final.png 在计时结束后保存最终窗口截图。
