# 测试媒体

`tests/fixtures/sample.mp4` 与 `sample-short.mp4` 是本项目生成的合成测试视频，用于真实解码、定位、循环和同步回归。`demo/` 下同名文件是它们的副本，未使用影视片段或用户视频。项目原创测试材料按仓库 MIT 许可证分发；编码和解码工具的许可证见其各自声明。

| 文件 | 时长 | 视频 | 音频 |
| --- | --- | --- | --- |
| `sample.mp4` | 12 秒 | 640×360、24 fps、H.264 | AAC |
| `sample-short.mp4` | 6 秒 | 640×360、24 fps、H.264 | AAC |

回归测试依赖时长和编码，而非文件的某个固定字节摘要。执行现有测试无需安装 FFmpeg 命令行工具，PySide6 的 Qt Multimedia 运行库提供解码后端。

## 生成同类媒体

如果需要重建测试输入，可使用 FFmpeg 的 `testsrc2` 和 `sine` 合成源生成相同规格的媒体。以下命令生成**同类测试内容**，不保证重现已提交 MP4 的逐字节结果；编码器版本和参数会影响文件大小、画面和时间戳。新的测试输入应重新执行完整媒体回归。

需将支持 `libx264` 和 AAC 编码的 `ffmpeg` 放入 PATH，在项目根目录 PowerShell 执行。输出放在忽略目录中，`-n` 保留已有同名文件：

```powershell
New-Item -ItemType Directory -Path artifacts\media -Force | Out-Null

ffmpeg -nostdin -n -f lavfi -i 'testsrc2=size=640x360:rate=24:duration=12' -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=12' -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -b:a 128k -t 12 -movflags +faststart artifacts\media\sample.mp4

ffmpeg -nostdin -n -f lavfi -i 'testsrc2=size=640x360:rate=24:duration=6' -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=6' -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -b:a 128k -t 6 -movflags +faststart artifacts\media\sample-short.mp4
```

更换版本控制内的样例时，保持 `tests/fixtures/` 与 `demo/` 的同名文件一致，并重新检查所有 `.gstudio` 示例、真实播放测试和媒体基准。现有演示工作区使用相对路径，移动时保留同目录 MP4 即可。

命令参数依据 FFmpeg 官方的 [合成源滤镜文档](https://github.com/FFmpeg/FFmpeg/blob/n7.1.2/doc/filters.texi) 和 [编码器文档](https://github.com/FFmpeg/FFmpeg/blob/n7.1.2/doc/encoders.texi)。这里使用的外部 `ffmpeg` 命令行程序只用于生成媒体，不会被构建脚本打包进播放器。
