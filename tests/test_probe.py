"""probe_video：用参数已知的合成视频核对测量值。

响度的参照值不依赖被测代码：双声道 997Hz 正弦、单声道幅度 A，按 BS.1770 应为 20·log10(A) LUFS
（1kHz 处 K 加权增益约 +0.7dB，与 -0.691 常数相互抵消）。标定实测 A=0.1/0.25/0.5 分别为 -20.0/-12.0/-6.0。
"""
import math
import re

import pytest

import media
import video_review as vr
from bugs import bug

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def spans(info):
    return [tuple(float(x) for x in re.findall(r"[\d.]+", s)) for s in info["黑帧区间"]]


def freezes(info):
    return [float(s.rstrip("s")) for s in info["冻结帧起点"]]


def test_basic_video_parameters():
    info = vr.probe_video(media.video(320, 180, 30, 4, audio=0.25))
    assert info["时长(秒)"] == pytest.approx(4.0, abs=0.05)
    assert info["视频编码"] == "h264" and info["分辨率"] == "320x180"
    assert info["画幅"] == "1.778 (横屏)" and info["帧率"] == 30.0
    assert (info["音频编码"], info["采样率"], info["声道"]) == ("aac", 48000, "stereo")
    assert "音频" not in info


@pytest.mark.parametrize("w,h,label", [(1080, 1920, "0.562 (竖屏)"), (360, 360, "1.000 (方形)"), (640, 360, "1.778 (横屏)")])
def test_orientation(w, h, label):
    info = vr.probe_video(media.video(w, h, 30, 0.5))
    assert info["分辨率"] == f"{w}x{h}" and info["画幅"] == label


@pytest.mark.parametrize("fps", [24, 25, 60])
def test_frame_rate(fps):
    assert vr.probe_video(media.video(fps=fps, dur=1))["帧率"] == fps


@pytest.mark.parametrize("amp", [0.1, 0.25, 0.5])
def test_integrated_loudness_matches_theory(amp):
    info = vr.probe_video(media.video(dur=3, audio=amp))
    assert info["综合响度(LUFS)"] == pytest.approx(20 * math.log10(amp), abs=0.7)


def test_true_peak_tracks_amplitude():
    info = vr.probe_video(media.video(dur=3, audio=0.5))
    assert float(info["真峰值(dBTP)"]) == pytest.approx(20 * math.log10(0.5), abs=1.0)


def test_clipping_reports_positive_true_peak():
    info = vr.probe_video(media.video(dur=3, audio=1.4))
    assert float(info["真峰值(dBTP)"]) > 0


def test_silence():
    info = vr.probe_video(media.video(dur=3, audio="silence"))
    assert info["综合响度(LUFS)"] == -70.0 and info["真峰值(dBTP)"] == "-inf"


def test_no_audio_track_skips_loudness():
    info = vr.probe_video(media.video(dur=2))
    assert info["音频"] == "无音轨"
    assert not {"综合响度(LUFS)", "真峰值(dBTP)", "音频编码"} & info.keys()


def test_webm_vp9_opus():
    info = vr.probe_video(media.video(dur=2, audio=0.25, ext="webm"))
    assert (info["视频编码"], info["音频编码"], info["分辨率"]) == ("vp9", "opus", "320x180")


def test_hour_long_duration_parsed():
    p = media.make("hour.mp4", "-f", "lavfi", "-i", "testsrc2=s=16x16:r=1:d=3725", *media.H264)
    assert vr.probe_video(p)["时长(秒)"] == pytest.approx(3725, abs=1)


def test_path_with_chinese_and_spaces(tmp_path):
    src = media.video(dur=1)
    p = tmp_path / "成片 最终版 (1).mp4"
    p.write_bytes(src.read_bytes())
    assert vr.probe_video(p)["分辨率"] == "320x180"


# ---------- 黑帧 / 冻结帧 ----------

def test_clean_video_has_no_black_or_freeze():
    info = vr.probe_video(media.video(dur=4))
    assert info["黑帧区间"] == [] and info["冻结帧起点"] == []


def test_black_segment_located():
    (a, b), = spans(vr.probe_video(media.black_segment(2.0, 2.5)))
    assert a == pytest.approx(2.0, abs=0.04) and b == pytest.approx(2.5, abs=0.07)


def test_black_just_above_threshold_detected():
    # 阈值 0.2 秒：0.3 秒的黑段必须报出（防止阈值被悄悄放大）
    assert len(spans(vr.probe_video(media.black_segment(1.0, 1.3)))) == 1


def test_black_shorter_than_threshold_ignored():
    assert spans(vr.probe_video(media.black_segment(2.0, 2.1))) == []


def test_dark_scene_is_not_black():
    assert spans(vr.probe_video(media.video(dur=4, vf="eq=brightness=-0.42"))) == []


def test_freeze_located():
    (t,) = freezes(vr.probe_video(media.freeze_at(120, 45)))  # 第 4.0 秒起冻结 1.5 秒
    assert t == pytest.approx(4.0, abs=0.07)


def test_freeze_shorter_than_threshold_ignored():
    assert freezes(vr.probe_video(media.freeze_at(120, 20))) == []  # 0.7 秒


# ---------- 异常输入 ----------

def test_rotation_metadata_respected():
    info = vr.probe_video(media.rotated(90))
    assert info["分辨率"] == "180x320" and "竖屏" in info["画幅"]


def _bad_inputs(tmp_path):
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\xff" * 2000)
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    return {"corrupt": corrupt, "empty": empty, "missing": tmp_path / "missing.mp4", "audio_only": media.audio_only()}


@pytest.mark.parametrize("kind", ["corrupt", "empty", "missing", "audio_only"])
def test_unusable_input_is_reported(tmp_path, kind):
    path = _bad_inputs(tmp_path)[kind]
    try:
        info = vr.probe_video(path)
    except Exception:
        return  # 抛错可以接受
    assert "错误" in info, f"{kind} 未报错，返回了残缺参数：{info}"


# ---------- 解析器单元（固定 stderr 文本） ----------

FFMPEG_OUT = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'x.mp4':
  Duration: 01:02:03.45, start: 0.000000, bitrate: 1200 kb/s
  Stream #0:0[0x1](und): Video: hevc (Main 10) (hvc1 / 0x31637668), yuv420p10le(tv, bt2020nc/bt2020/smpte2084), 3840x2160 [SAR 1:1 DAR 16:9], 900 kb/s, 29.97 fps, 29.97 tbr, 30k tbn (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, 5.1, fltp, 128 kb/s (default)
"""


def test_parse_stderr_fields(monkeypatch):
    monkeypatch.setattr(vr, "run_ffmpeg", lambda args: FFMPEG_OUT if "-af" not in args and "-vf" not in args else "")
    info = vr.probe_video("x.mp4")
    assert info["时长(秒)"] == 3723.45 and info["视频编码"] == "hevc" and info["分辨率"] == "3840x2160"
    assert info["帧率"] == 29.97 and (info["音频编码"], info["采样率"], info["声道"]) == ("aac", 44100, "5.1")
