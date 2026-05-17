# Agent 解说词工作流

## 运行前置分析

```bash
python3 scripts/video_recap.py <video> --tts edge-tts --context "背景"
```

Pipeline 会完成场景检测、ASR、VLM 分析和静音检测，然后暂停，并在 `work_dir/` 里写出：

| 文件 | 内容 |
|------|------|
| `agent_narration_brief.md` | 给 Agent 写解说词用的场景、时长、安静窗口和字数预算 |
| `vlm_analysis.json` | 每场景的画面描述、深度分析、帧级事实 (`frame_facts`) |
| `asr_result.json` | 语音转文字结果，含时间戳和对白文本 |
| `silence_periods.json` | 静音窗口列表，用于确定解说放置位置 |

写稿时优先读 `agent_narration_brief.md`，需要查证细节时再看原始 JSON。

## 背景调研（推荐）

详细操作指南见 `references/research-guide.md`。如果 `--context` 包含节目/电影名称，且当前环境有可用搜索/浏览能力，推荐先调研并写入 `work_dir/background_research.json`：

```json
{
  "synopsis": "...",
  "characters": {"角色名": "简介"},
  "worldbuilding": "...",
  "episode_context": "..."
}
```

## narration.json 字段

```json
[
  {
    "start": 5.0,
    "end": 12.0,
    "narration": "解说文本。",
    "pause_after_ms": 600,
    "overlaps_speech": false
  }
]
```

| 字段 | 说明 |
|------|------|
| `start` | 解说开始时间（秒） |
| `end` | 解说结束时间（秒） |
| `narration` | 解说文本 |
| `pause_after_ms` | 段后停顿毫秒数，默认 600 |
| `overlaps_speech` | 是否与原声对白重叠；优先 false |

## 写作规则

1. **不要看图说话**：观众看得见动作和表情，解说应讲动机、关系、潜台词和剧情意义。
2. **优先安静窗口**：尽量放在 brief 给出的 quiet windows；重要对白不要盖住。
3. **控制字数**：每段字数 ≤ `(end - start - 0.6) × 3`，宁短不长。
4. **保留原声节奏**：对白精彩处可以不写解说，让原片说话。
5. **用已知角色名**：如果 `--context` 或调研提供了角色名，优先使用角色名。
6. **完整句子**：以句号、问号或感叹号结束，不写半句话。

## 继续 TTS + 组装

写完 `narration.json` 后执行：

```bash
python3 scripts/video_recap.py <video> --resume work_dir
```

如果改过已经配音的 `narration.json`，先清理旧 TTS 缓存：

```bash
rm -rf work_dir/tts_segments/ work_dir/.step_tts.done \
  work_dir/.step_assemble.done work_dir/tts_meta.json
```
