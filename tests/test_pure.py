"""Pure function unit tests for video-recap modules."""
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'video-recap' / 'scripts'))

from common import _retry_after_seconds, get_video_duration
from config import CONFIG, env_bool, env_int, normalize_api_url
from detect import detect_scenes
from extract import extract_frames
from pipeline import _command_available, run_pipeline
from narration import _text_char_count
from tts import _detect_tts_engine, _parse_rate_offset, synthesize_tts
from assemble import _seconds_to_srt_time
from vlm import analyze_scenes


def test_text_char_count():
    assert _text_char_count("hello") == 5
    assert _text_char_count("你好世界") == 4
    assert _text_char_count("") == 0


def test_parse_rate_offset():
    assert _parse_rate_offset("+0%") == 0.0
    assert _parse_rate_offset("+20%") == 0.2
    assert _parse_rate_offset("-10%") == -0.1
    assert _parse_rate_offset("+5%") == 0.05


def test_seconds_to_srt_time():
    # 3661.5s = 1h 1m 1.5s
    result = _seconds_to_srt_time(3661.5)
    assert result.startswith("01:01:01")
    # 0s
    assert _seconds_to_srt_time(0) == "00:00:00,000"


def test_get_video_duration_returns_zero_for_unparseable_output(monkeypatch):
    def fake_run_cmd(cmd):
        return CompletedProcess(cmd, 0, stdout="N/A\n", stderr="")

    monkeypatch.setattr("common.run_cmd", fake_run_cmd)
    assert get_video_duration("bad.mp4") == 0.0


def test_retry_after_seconds_accepts_malformed_header():
    assert _retry_after_seconds("not-a-number-or-date", 4) == 4


def test_normalize_api_url_accepts_base_or_full_endpoint():
    assert normalize_api_url("https://example.com/v1") == "https://example.com/v1/chat/completions"
    assert normalize_api_url("https://example.com/v1/") == "https://example.com/v1/chat/completions"
    assert normalize_api_url("https://example.com/v1/chat/completions") == "https://example.com/v1/chat/completions"


def test_env_int_and_bool_helpers_tolerate_bad_values(monkeypatch):
    monkeypatch.setenv("BAD_INT", "not-an-int")
    monkeypatch.setenv("LOW_INT", "-3")
    monkeypatch.setenv("YES_BOOL", "on")
    monkeypatch.setenv("NO_BOOL", "0")

    assert env_int("BAD_INT", 8, minimum=1) == 8
    assert env_int("LOW_INT", 8, minimum=1) == 1
    assert env_bool("YES_BOOL") is True
    assert env_bool("NO_BOOL", default=True) is False


def test_detect_scenes_respects_zero_threshold(monkeypatch, tmp_path):
    commands = []

    def fake_run_cmd(cmd, **kwargs):
        commands.append(cmd)
        return CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("detect.run_cmd", fake_run_cmd)
    monkeypatch.setattr("detect.get_video_duration", lambda video: 12.5)
    scenes = detect_scenes(Path("video.mp4"), tmp_path, threshold=0.0)

    assert "scdet=threshold=0" in commands[0]
    assert scenes == [{"start": 0.0, "end": 12.5}]


def test_extract_frames_rejects_non_positive_fps(tmp_path):
    with pytest.raises(ValueError, match="fps 必须大于 0"):
        extract_frames(Path("video.mp4"), tmp_path, fps=0)


def test_analyze_scenes_rejects_empty_frames(tmp_path):
    with pytest.raises(RuntimeError, match="frames 为空"):
        analyze_scenes([{"start": 0.0, "end": 1.0}], [], tmp_path)


def test_synthesize_tts_handles_empty_narration(monkeypatch, tmp_path):
    monkeypatch.setitem(__import__("config").CONFIG, "tts_engine", "say")
    segments, engine = synthesize_tts([], tmp_path)

    assert segments == []
    assert engine == "say"


def test_synthesize_tts_raises_on_failed_segment_by_default(monkeypatch, tmp_path):
    narration = [
        {"start": 0.0, "end": 1.0, "narration": "第一段。"},
        {"start": 1.0, "end": 2.0, "narration": "第二段。"},
    ]

    def fake_synthesize_segment(i, seg, narration_data, tts_dir, engine):
        if i == 1:
            raise RuntimeError("network timeout")
        return {
            "index": i,
            "start": seg["start"],
            "end": seg["end"],
            "narration": seg["narration"],
            "audio_path": str(tts_dir / f"narr_{i:03d}.wav"),
            "audio_duration": 0.5,
        }

    monkeypatch.setitem(CONFIG, "tts_engine", "say")
    monkeypatch.setitem(CONFIG, "tts_workers", 2)
    monkeypatch.setitem(CONFIG, "allow_partial_tts", False)
    monkeypatch.setattr("tts._synthesize_segment", fake_synthesize_segment)

    with pytest.raises(RuntimeError, match="TTS 失败 1/2 段"):
        synthesize_tts(narration, tmp_path)


def test_synthesize_tts_allows_partial_when_configured(monkeypatch, tmp_path):
    narration = [
        {"start": 0.0, "end": 1.0, "narration": "第一段。"},
        {"start": 1.0, "end": 2.0, "narration": "第二段。"},
    ]

    def fake_synthesize_segment(i, seg, narration_data, tts_dir, engine):
        if i == 1:
            raise RuntimeError("network timeout")
        return {
            "index": i,
            "start": seg["start"],
            "end": seg["end"],
            "narration": seg["narration"],
            "audio_path": str(tts_dir / f"narr_{i:03d}.wav"),
            "audio_duration": 0.5,
        }

    monkeypatch.setitem(CONFIG, "tts_engine", "say")
    monkeypatch.setitem(CONFIG, "tts_workers", 2)
    monkeypatch.setitem(CONFIG, "allow_partial_tts", True)
    monkeypatch.setattr("tts._synthesize_segment", fake_synthesize_segment)

    segments, engine = synthesize_tts(narration, tmp_path)

    assert engine == "say"
    assert [s["index"] for s in segments] == [0]


def test_detect_tts_engine_prefers_edge_tts(monkeypatch):
    monkeypatch.setattr("tts.shutil.which", lambda cmd: "/usr/bin/edge-tts" if cmd == "edge-tts" else None)

    assert _detect_tts_engine() == "edge-tts"


def test_command_available_checks_path_and_executable_name(tmp_path, monkeypatch):
    executable = tmp_path / "tool"
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setattr("pipeline.shutil.which", lambda cmd: "/bin/echo" if cmd == "echo" else None)

    assert _command_available(str(executable))
    assert _command_available("echo")
    assert not _command_available("missing-command")


def test_step_tts_runs_from_cached_narration_without_api(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "narration.json").write_text(
        '[{"start":0.0,"end":3.0,"narration":"你好世界。"}]',
        encoding="utf-8",
    )

    monkeypatch.setitem(CONFIG, "api_key", "")
    monkeypatch.setitem(CONFIG, "fps", 1)
    monkeypatch.setattr("pipeline.check_prerequisites", lambda skip_asr=False: True)
    monkeypatch.setattr("pipeline.get_video_duration", lambda path: 3.0)
    monkeypatch.setattr("pipeline.api_call", lambda payload: (_ for _ in ()).throw(AssertionError("API should not be called")))
    monkeypatch.setattr("pipeline.synthesize_tts", lambda narration, wd: ([{
        "index": 0,
        "start": 0.0,
        "end": 3.0,
        "narration": narration[0]["narration"],
        "audio_path": str(wd / "narr_000.wav"),
        "audio_duration": 1.0,
    }], "say"))

    result = run_pipeline(video, step="tts", resume_dir=work_dir)

    assert result["engine"] == "say"
    assert len(result["segments"]) == 1
    assert (work_dir / ".step_tts.done").exists()
    assert (work_dir / "tts_meta.json").exists()


def test_full_pipeline_pauses_for_agent_brief_without_script_api(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    output = tmp_path / "out"

    monkeypatch.setitem(CONFIG, "api_key", "test-key")
    monkeypatch.setitem(CONFIG, "fps", 1)
    monkeypatch.setitem(CONFIG, "skip_narrative_analysis", True)
    monkeypatch.setattr("pipeline.check_prerequisites", lambda skip_asr=False: True)
    monkeypatch.setattr("pipeline.get_video_duration", lambda path: 8.0)
    monkeypatch.setattr("pipeline.api_call", lambda payload: {"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr("pipeline.extract_frames", lambda video_path, work_dir: [work_dir / "frames" / "frame_00001.jpg"])
    monkeypatch.setattr("pipeline.detect_scenes", lambda video_path, work_dir, threshold: [{"start": 0.0, "end": 8.0}])
    monkeypatch.setattr("pipeline.transcribe_audio", lambda video_path, work_dir: [])
    monkeypatch.setattr("pipeline.detect_silence_periods", lambda video_path, work_dir, asr: [{"start": 1.0, "end": 6.0, "duration": 5.0, "has_speech": False}])
    monkeypatch.setattr("pipeline.analyze_scenes", lambda scenes, frames, work_dir: [{
        "scene_id": 0,
        "start": 0.0,
        "end": 8.0,
        "description": "角色沉默对视。",
        "depth_analysis": "关系紧张。",
    }])
    monkeypatch.setattr("pipeline.synthesize_tts", lambda narration, wd: (_ for _ in ()).throw(AssertionError("TTS should wait for narration")))

    result = run_pipeline(video, output_dir=output)

    work_dir = Path(result["work_dir"])
    assert result["status"] == "paused"
    assert (work_dir / "agent_narration_brief.md").exists()
    assert not (work_dir / "narration.json").exists()
    assert not (work_dir / ".step_script.done").exists()


def test_resume_validates_existing_agent_narration_without_api(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / ".step_extract.done").write_text("ok")
    (work_dir / ".step_detect.done").write_text("ok")
    (work_dir / ".step_asr.done").write_text("ok")
    (work_dir / ".step_silence.done").write_text("ok")
    (work_dir / ".step_vlm.done").write_text("ok")
    (work_dir / "scenes.json").write_text('[{"start":0.0,"end":6.0}]')
    (work_dir / "asr_result.json").write_text('[]')
    (work_dir / "silence_periods.json").write_text('[{"start":0.0,"end":6.0,"duration":6.0,"has_speech":false}]')
    (work_dir / "vlm_analysis.json").write_text('[{"scene_id":0,"start":0.0,"end":6.0,"description":"测试场景"}]')
    (work_dir / "narration.json").write_text('[{"start":0.5,"end":5.5,"narration":"他终于意识到，沉默比争吵更伤人。"}]')

    monkeypatch.setitem(CONFIG, "api_key", "")
    monkeypatch.setitem(CONFIG, "fps", 1)
    monkeypatch.setitem(CONFIG, "skip_narrative_analysis", True)
    monkeypatch.setattr("pipeline.check_prerequisites", lambda skip_asr=False: True)
    monkeypatch.setattr("pipeline.get_video_duration", lambda path: 6.0)
    monkeypatch.setattr("pipeline.api_call", lambda payload: (_ for _ in ()).throw(AssertionError("API should not be called")))
    monkeypatch.setattr("pipeline.synthesize_tts", lambda narration, wd: ([{
        "index": 0,
        "start": narration[0]["start"],
        "end": narration[0]["end"],
        "narration": narration[0]["narration"],
        "audio_path": str(wd / "narr_000.wav"),
        "audio_duration": 1.0,
    }], "say"))
    monkeypatch.setattr("pipeline.assemble_video", lambda video_path, tts_segments, wd, output_path: output_path.write_bytes(b"mp4"))

    result = run_pipeline(video, resume_dir=work_dir)

    assert result["tts_engine"] == "say"
    assert (work_dir / ".step_script.done").exists()
    assert (work_dir / "output.mp4").exists()
