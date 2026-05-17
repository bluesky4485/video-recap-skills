---
name: video-recap
description: >
 Generate Chinese voiceover / narration / recap videos from an input video.
 Use when the user provides a video file (.mp4 / .mov / .mkv / .webm) and asks
 to add narration, generate voiceover, dub, summarize, or produce a recap.
 Supports: 短剧 / 电视剧 / 电影 / 纪录片 / 科普视频.
 Pipeline: scene detection → VLM analysis → ASR → agent writes narration.json →
 TTS → assembly.
 触发词: 视频解说, 视频旁白, 生成解说, 视频recap, video recap, voiceover,
 narration, auto-dub, recap.
---

## References（按需读取）

| 何时读 | 文档 |
|---|---|
| **写 narration.json 之前必读** | `references/agent-mode-workflow.md` |
| 撰写解说词时（风格 / 反幻觉 / 字数公式） | `references/prompt-templates.md` |
| 读写中间 JSON | `references/data-schema.md` |
| 改 CLI 参数或环境变量 | `references/parameters.md` |
| 中断恢复 / 局部重跑 | `references/pipeline-resume.md` |
| 调 ducking / zone / volume | `references/internal-config.md` |

## 安装与依赖

```bash
brew install ffmpeg && pip3 install edge-tts
export OPENAI_API_KEY=***
export OPENAI_MODEL=doubao-seed-2-0-lite-260428
# 可选：OPENAI_API_URL
```

推荐安装方式：

```bash
git clone <repo> /tmp/video-recap-repo
ln -s /tmp/video-recap-repo/skills/video-recap ~/.claude/skills/video-recap
```

## 使用流程

### 1. 运行前置分析（自动暂停）

```bash
python3 scripts/video_recap.py <video> --tts edge-tts --context "背景"
```

### 2. 撰写解说词

读取 `work_dir/agent_narration_brief.md` 以及 vlm_analysis / asr_result / silence_periods，写 `work_dir/narration.json`。
字段格式与写作规则见 `agent-mode-workflow.md`。

### 3. （可选）背景调研

使用任意可用搜索/浏览方式调研，写 `work_dir/background_research.json`；没有工具就跳过。

### 4. 继续 TTS + 组装

```bash
python3 scripts/video_recap.py <video> --resume work_dir
```

⚠️ 改完 narration.json 后如需重配音，删 `tts_segments/`、`.step_tts.done`、`.step_assemble.done` 和 `tts_meta.json`。

## 自检

```bash
python3 scripts/video_recap.py --doctor
```

## 输出

- `recap_<video>.mp4` — 最终视频
- `subtitles.srt` — 字幕
- `work_dir/agent_narration_brief.md` — 解说词写作 brief
- `work_dir/narration.json` — Agent 写的解说词
- `work_dir/` — 所有中间 JSON
