# GridStudio 1.0.0 验证记录

**简体中文** | [English](validation-1.0.0.en.md)

验证日期：**2026-10-22**。环境为本机 Windows 11 x64、Python 3.12.14、PySide6/Qt 6.10.2。

本记录区分发布前既有的功能回归与正式版重新构建验证。远程 CI 状态见[仓库 Actions](https://github.com/ssjjrrr/GridStudio/actions)。

## 发布前功能回归

在 `offscreen` Qt 平台下，同时开启 `GRIDSTUDIO_REAL_HOVER_SEEK=1` 和 `GRIDSTUDIO_REAL_HOVER_TRANSPORT=1`，执行完整测试套件。

**结果：241 passed，191 subtests passed，耗时 39.82 秒，无跳过。**

覆盖真实 H.264 解码与定位、循环同步、复制变换、工作区往返、合成像素、透明留白与鼠标穿透、画布编辑、悬停播放/音量/进度、窗格生命周期、性能工作量约束及独立子进程定位死锁回归。两个真实悬停测试在这次完整回归中与其他测试同进程执行。

复现入口，在源码根目录 PowerShell 中运行：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:GRIDSTUDIO_REAL_HOVER_SEEK = '1'
$env:GRIDSTUDIO_REAL_HOVER_TRANSPORT = '1'
.\.venv\Scripts\python.exe -m pytest tests -q -o faulthandler_timeout=30
```

## Windows 原生窗口与真实播放

使用原生 `windows` Qt 平台，同时播放四路 640×360 H.264/AAC 测试视频，执行 8 次真实复制后删除操作。

- 存量画面的 Hide、ParentChange 事件均为 0，原有播放器与图层继续保留。
- 操作期间四个存量视频分别收到 **20、21、20、20** 个有效新解码帧。
- 同步 A/B 区间为 1000–2000 ms，确认两次回绕。
- 暂停后控制器定时器停止，恢复同步播放后重新启动；还原为独立原生整段循环后停止轮询。
- 关闭窗口后控制器保持关闭，没有被媒体状态信号重新启动。

另完成 **20 轮布局/聚焦往返，共 80 次切换**，以及 **20 次暂停状态下的同步定位**，均通过。上述新帧数量是该操作阶段的观测计数，不是播放 FPS 或最大解码能力的测量。

## 重建便携版

1.0.0 的便携版重新构建后，直接启动实际 `GridStudio.exe`，使用 Windows 原生窗口验证以下工作区：

| 场景 | 视频来源数 | 结果 |
| --- | ---: | --- |
| 自由画布编辑 | 3 | 有效解码帧、NoError、退出码 0、截图成功 |
| 叠放与悬停播放控件 | 2 | 有效解码帧、NoError、退出码 0、截图成功 |
| 同步 A/B 循环 | 2 | 有效解码帧、NoError、退出码 0、截图成功 |

三个场景的 JSON 诊断均记录版本 `1.0.0`、`capture_saved=true`、`passed=true`；每个已打开来源均有有效视频帧、正时长和 `NoError`。实际截图已目视检查视频显示、播放/音量控件、A/B 标记对齐和透明叠层。

项目首页另使用三个公开影片文件的四路非重叠画布截图，来自同一 1.0.0 便携版。四路均确认有效帧、正时长和 `NoError`，并目视检查四宫格边界无缝衔接；素材和画面裁剪说明见[预览素材来源与署名](https://github.com/ssjjrrr/GridStudio/blob/v1.0.0/docs/preview-sources.md)。

同时核对：

- `licenses/SOURCES.json` 中 8 份许可证文件的字节长度和 SHA-256 摘要全部匹配。
- Windows EXE 文件属性的 `FileVersion` 与 `ProductVersion` 均为 `1.0.0`，与应用版本一致。
- Qt、Multimedia 与 FFmpeg 所需共享库齐全。
- 便携目录未带入冲突的 `icuuc.dll` 或 `icudt78.dll`。

## 范围

本次验证对应上述本机 Windows 11 环境，**未在其他电脑或 Windows 10 上复测**。功能回归的真实播放输入为 640×360，首页截图另使用 1280×720 和 960×540 素材；性能材料中的 4K 场景是合成视频帧，不能据此推断真实 4K 多路解码能力。

本轮性能样本和查询计数另见源码 `benchmarks/performance.json`；便携目录中对应 `PERFORMANCE.json`。此记录不替代其他编码、设备、分辨率和长时间运行场景的验证。
