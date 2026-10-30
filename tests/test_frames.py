"""extract_frames：取帧时间点、实际截到的帧、缩放、边界时长。

用"帧号编码视频"核对截到的是哪一帧：每帧把自己的帧号写进亮度，解码 JPEG 就能读回帧号。
"""
import pytest
from hypothesis import given, settings, strategies as st

import media
import video_review as vr
from bugs import bug

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_frames_are_the_requested_frames(tmp_path):
    fps = 25
    frames = vr.extract_frames(media.frame_index_video(fps, 10), 10, 4, tmp_path)
    times = [t for t, _ in frames]
    # 4 个段中点 3.88 / 5.62 / 7.38 / 9.12，间隔超过 1 秒的地方补在中间
    assert times == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.19, 3.88, 4.75, 5.62, 6.5, 7.38, 8.25, 9.12, 9.9]
    for t, p in frames:
        assert media.decode_frame_index(p) in (int(t * fps), int(t * fps) + 1), f"t={t}"


def test_output_names_and_files(tmp_path):
    frames = vr.extract_frames(media.frame_index_video(), 10, 2, tmp_path)
    assert all(p.exists() and p.name == f"frame_{t:07.2f}.jpg" for t, p in frames)
    assert len({p for _, p in frames}) == len(frames)


@pytest.mark.parametrize("duration,times", [
    (3.0, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 2.9]),
    (2.0, [0.0, 0.5, 1.0, 1.5, 1.9]),
    (0.3, [0.0, 0.2]),
    (0.05, [0.0]),
    (0, [0]),
])
def test_short_durations(tmp_path, duration, times):
    got = [t for t, _ in vr.extract_frames(media.frame_index_video(), duration, 3, tmp_path)]
    assert got == pytest.approx(times)


def test_large_frames_scaled_to_768_wide(tmp_path):
    from PIL import Image
    frames = vr.extract_frames(media.video(1080, 1920, 30, 0.5), 0.5, 2, tmp_path)
    assert frames and all(Image.open(p).size == (768, 1366) for _, p in frames)


def test_small_frames_not_upscaled(tmp_path):
    from PIL import Image
    (_, p), *_ = vr.extract_frames(media.video(320, 180, 30, 1), 1, 1, tmp_path)
    assert Image.open(p).size == (320, 180)


def test_missing_file_gives_no_frames(tmp_path):
    assert vr.extract_frames(tmp_path / "missing.mp4", 5, 2, tmp_path) == []


@settings(max_examples=300, deadline=None)
@given(st.floats(0, 600, allow_nan=False).map(lambda x: round(x, 2)), st.integers(1, 30))
def test_schedule_property(duration, n):
    """不调 ffmpeg，只按规格逐条检查时间表，不复刻实现的算法。

    规格：前 3 秒每 0.5 秒一帧；(3, duration] 均分 n 段、每段恰好一帧且在中点（两位小数）；最后一帧 duration-0.1。
    """
    calls = []

    class Done:
        pass

    import subprocess
    real = subprocess.run
    try:
        subprocess.run = lambda cmd, **k: calls.append(float(cmd[cmd.index("-ss") + 1])) or Done()
        vr.extract_frames("x.mp4", duration, n, "Z:/nonexistent")
    finally:
        subprocess.run = real
    assert calls == sorted(set(calls)), "升序且不重复"
    assert all(0 <= t <= duration for t in calls), "不越界"
    # 尾帧不一定排最后：最后一段短于 0.2 秒时，段中点会晚于 duration-0.1（如 duration=4、n=6 时 3.92 > 3.9）
    tail = round(max(duration - 0.1, 0), 9)
    assert tail in [round(t, 9) for t in calls], "尾帧"
    hook = {round(t, 9) for t in calls if t < 3} - {tail}  # 尾帧可能落在前 3 秒（短视频），单独核对过了
    assert hook == {t for t in (0, 0.5, 1, 1.5, 2, 2.5) if t < duration} - {tail}, "前 3 秒恰好是 duration 之内的钩子帧"
    if duration > 3:
        seg = (duration - 3) / n
        for i in range(n):
            lo, hi, mid = 3 + seg * i, 3 + seg * (i + 1), 3 + seg * (i + 0.5)
            inside = [t for t in calls if lo - 0.006 <= t <= hi + 0.006 and abs(t - mid) <= 0.0051]
            assert inside, f"第 {i} 段 [{lo:.3f},{hi:.3f}] 中点 {mid:.3f} 处没有帧"
    assert len(calls) <= vr.MAX_FRAMES, "总帧数不超过上限"
    if len(calls) < vr.MAX_FRAMES:
        later = [t for t in calls if t >= 2.5]
        assert all(b - a <= vr.MAX_GAP + 0.011 for a, b in zip(later, later[1:])), "没到上限时相邻帧间隔 ≤ MAX_GAP"


def test_zero_frames_requested(tmp_path):
    frames = vr.extract_frames(media.frame_index_video(), 10, 0, tmp_path)
    assert [t for t, _ in frames] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 9.9]


def test_tail_frame_when_audio_longer_than_video(tmp_path):
    p = media.audio_longer_than_video(2, 4)
    dur = vr.probe_video(p)["时长(秒)"]
    times = [t for t, _ in vr.extract_frames(p, dur, 3, tmp_path)]
    assert times and times[-1] >= 1.8  # 视频流最后 0.2 秒内应有一帧（CTA）
