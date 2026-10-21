# 开发、测试与构建

以下命令都在项目根目录的 PowerShell 中执行。主要验证环境为 Windows x64、Python 3.12.14、PySide6/Qt 6.10.2；CI 使用相同 Python 补丁版本，与当前便携运行时声明保持一致。

## 建立环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe run.py
```

`requirements-dev.txt` 包含运行依赖、pytest 和 PyInstaller。运行应用只需 `requirements.txt`。Python 路径无需写入代码；构建路径以脚本所在项目根目录为准。

## 运行测试

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_MEDIA_BACKEND = 'ffmpeg'
.\.venv\Scripts\python.exe -m pytest tests -q -o faulthandler_timeout=30
```

测试需要版本控制中的 `tests/fixtures/sample.mp4` 和 `sample-short.mp4`。它们是真实 H.264/AAC 测试文件；无需额外安装 FFmpeg 命令行工具。相关来源和重建方法见 [test-media.md](test-media.md)。

主套件覆盖模型、真实播放/定位/复制、循环与同步、画布合成像素、编辑手势、留白透出、悬停控件和播放器释放。默认会跳过下面两项由环境开关控制的真实悬停测试。CI 分别运行以便隔离诊断，本地可使用相同方式：

```powershell
$env:GRIDSTUDIO_REAL_HOVER_SEEK = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_hover_controls.py::test_real_video_hover_seek_updates_paused_decoder_frame -q -o faulthandler_timeout=30
Remove-Item Env:GRIDSTUDIO_REAL_HOVER_SEEK

$env:GRIDSTUDIO_REAL_HOVER_TRANSPORT = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_hover_transport.py::test_real_media_buttons_play_pause_and_volume_update_audio -q -o faulthandler_timeout=30
Remove-Item Env:GRIDSTUDIO_REAL_HOVER_TRANSPORT
```

也可同时设置 `GRIDSTUDIO_REAL_HOVER_SEEK=1` 和 `GRIDSTUDIO_REAL_HOVER_TRANSPORT=1` 后执行整个套件，在同一进程内包含这两项检查；它们不要求必须分进程。

每个命令必须以退出码 0 结束。`faulthandler_timeout` 在等待超过 30 秒时输出线程栈，但不终止测试。CI 通过步骤和 job 的超时停止挂起的任务，原生死锁回归另有子进程时间上限；请保留失败时的控制台输出。

### 原生定位死锁回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_seek_deadlock.py -q -o faulthandler_timeout=30
```

此测试在独立 Python 子进程里打开真实视频，建立受控的 Qt 连接锁竞争窗口，再通过修复后的媒体命令定位并检查实际解码帧。父进程给子进程 10 秒上限。它验证的是已构造的锁顺序，不代表重现所有历史间歇性卡死。常规 CI 只运行 `fixed` 模式。

## 构建 Windows 便携目录

```powershell
.\build.ps1
```

已有 `.venv` 时脚本复用它；否则使用 `-Python` 参数指定的 Python（默认 `python`）建立环境。为与第三方声明一致，请先确认环境中的 Python 版本：

```powershell
.\.venv\Scripts\python.exe -VV
```

构建脚本调用固定版本 PyInstaller 和 `GridStudio.spec`，生成 `dist/GridStudio/`，复制说明、`CHANGELOG.md`、许可证、完整 `licenses/` 和 `demo/`。基准说明保存为便携目录中的 `INTERACTION_PERFORMANCE.txt`，`benchmarks/performance.json` 复制为 `PERFORMANCE.json`。`GridStudio.exe` 依赖 `_internal`，整个目录需要一起分发。构建时过滤开发环境可能带入的同名 ICU DLL，使用受支持 Windows 的系统实现。

本地启动截图检查：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
@'
from pathlib import Path
import subprocess
bundle = Path('dist/GridStudio').resolve()
image = Path('artifacts/portable-smoke.png').resolve()
image.parent.mkdir(exist_ok=True)
subprocess.run([str(bundle / 'GridStudio.exe'), '--smoke-test', str(image),
                str(bundle / 'demo/自由画布与图层.gstudio')],
               cwd=bundle, check=True, timeout=30)
assert image.is_file() and image.with_suffix('.json').is_file()
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { throw '便携版启动检查失败' }
```

此命令检查打包程序能启动、解码工作区视频并输出窗口截图，以及同名 `.json` 媒体诊断；解码失败会返回非零退出码。定位、循环和同步的进一步断言由上面的媒体测试负责。正式发布前应在正常窗口环境目视检查便携版画面、悬停控件、拖动和全屏。

## 生成本地发布包

完成测试、构建和便携版验证后执行：

```powershell
.\.venv\Scripts\python.exe scripts\package_release.py --bundle dist\GridStudio --output dist\release
```

脚本从 `gridstudio.__version__` 读取版本，生成 `GridStudio-<版本>-Windows-x64.zip`、`GridStudio-<版本>-source.zip` 和 `GridStudio-<版本>-SHA256SUMS.txt`。便携包保留整个 `GridStudio/` 目录；源码包只收录指定的项目源码、文档、工作流、测试、示例和许可材料，不包含开发虚拟环境、Git 元数据与构建缓存。ZIP 写入后检查归档完整性，清单记录两个压缩包的 SHA-256。

`--bundle` 必须指向完整的便携目录，`--output` 必须位于该目录外。默认值分别为 `dist/GridStudio` 和 `dist`。此命令只生成本地归档，不创建远程仓库、不上传文件或创建 GitHub Release。

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) 在 push、pull request 或手动触发时运行。使用只读仓库权限，无发布令牌，不创建 Release。

工作流依次安装依赖、运行主套件、隔离运行两个真实悬停测试、构建便携版，并核对运行库、许可证摘要和打包启动截图/媒体诊断。原生死锁子进程、工作流步骤和 job 都有时间上限。结果和成功构建的完整便携目录作为 Actions artifacts 保存 14 天。

Python 3.12.14 属于仅发布源码的安全维护版本，`actions/setup-python` 无法为 Windows 提供该补丁版本。CI 使用固定提交的 `astral-sh/setup-uv` v10.3.0、uv 0.13.4 和 Python 3.12.14 的 Windows standalone 构建，通过 `uv venv --python 3.12.14 --seed .venv` 建立环境，并验证实际解释器版本。后续安装、测试和构建始终使用这个 `.venv`，不回退到 runner 的系统 Python。

上游说明与工作流所用 action 定义：

- [actions/checkout v6](https://github.com/actions/checkout/blob/v6/action.yml)
- [Python 3.12.14 的发行说明](https://www.python.org/downloads/release/python-31214/)
- [astral-sh/setup-uv v10.3.0](https://github.com/astral-sh/setup-uv/blob/1c37ad07a6a961277cf70c0d37d6f313000f5884/action.yml)
- [uv 的 GitHub Actions 集成](https://docs.astral.sh/uv/guides/integration/github/)
- [actions/upload-artifact v6](https://github.com/actions/upload-artifact/blob/v6/action.yml)

## 性能测量

```powershell
.\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --output interaction.json
.\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --media demo\sample.mp4 --output interaction-real.json
.\.venv\Scripts\python.exe benchmarks\workspace_bench.py --platform windows --panes 16 --cycles 20 --output artifacts\workspace-current.json
```

需要重跑发布前内部基线对照时，须另行提供当时的基线源码快照。输入其根目录并运行查询计数基准：

```powershell
$baselineProject = Read-Host '输入发布前内部基线源码根目录'
.\.venv\Scripts\python.exe benchmarks\playback_query_bench.py --baseline $baselineProject --output artifacts\playback-query-comparison.json
```

逐个运行基准以避免争抢资源。耗时场景每个构建至少运行三轮，保存不同输出文件并比较中位数；结果不是稳定的 CI 时间阈值，也不是解码帧率或输入到显示延迟。保留的发布前样本、环境和查询计数见 [performance.json](../benchmarks/performance.json)，审计边界见 [performance-audit.md](performance-audit.md)，方法与内部对照记录见 [benchmarks/README.txt](../benchmarks/README.txt)。这些数据沿用既有实测，不是正式版本改名后的新增测量；仅当前源码可复现当前侧结果，重跑前后对照还需对应的内部基线快照。
