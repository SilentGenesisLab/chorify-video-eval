"""B 层修复（REPORT_B §5）引入的程序测量：OCR、清晰度、模糊度、亮度、短静止、场景切换抽帧、及格线人审、判断细则。

都用参数已知的合成素材核对，不调用模型。
"""
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import media
import video_review as vr
from conftest import make_run

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def font(size):
    for name in ("msyh.ttc", "simhei.ttf", "NotoSansCJK-Regular.ttc", "wqy-microhei.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    pytest.skip("本机没有中文字体")


def card(tmp_path, text, name="kv.png", blur=0):
    im = Image.new("RGB", (720, 400), "white")
    ImageDraw.Draw(im).text((40, 120), text, fill="black", font=font(96))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    p = tmp_path / name
    im.save(p)
    return p


# ---------- OCR ----------

def test_ocr_reads_product_name(tmp_path):
    assert "星穹守望" in "".join(vr.ocr_text(card(tmp_path, "星穹守望")))


def test_ocr_distinguishes_lookalike_typo(tmp_path):
    # B 层 S05_asset_as_wrong_name：「守望」写成「守旺」，模型看图漏判；OCR 要读出差别
    right = "".join(vr.ocr_text(card(tmp_path, "星穹守望", "a.png")))
    wrong = "".join(vr.ocr_text(card(tmp_path, "星穹守旺", "b.png")))
    assert "守旺" in wrong and "守旺" not in right


def test_ocr_text_reaches_prompt(tmp_path):
    content, _ = vr.build_user_content([card(tmp_path, "星穹守旺")], None, None, 4, "", tmp_path)
    assert "程序识别的图上文字：" in content[1]["text"] and "守旺" in content[1]["text"]


def test_ocr_cached_by_content(tmp_path, monkeypatch):
    a = card(tmp_path, "星穹守望", "a.png")
    b = tmp_path / "b.png"
    b.write_bytes(a.read_bytes())
    vr.ocr_text(a)
    calls = []
    real = vr._OCR
    monkeypatch.setattr(vr, "_OCR", lambda p: calls.append(p) or real(p))
    assert vr.ocr_text(b) == vr.ocr_text(a) and calls == []  # 同内容不同文件名，不再识别


def test_frames_ocr_skips_unchanged_frames(tmp_path, monkeypatch):
    a, a2, c = card(tmp_path, "星穹守望", "1.png"), card(tmp_path, "星穹守望", "2.png"), card(tmp_path, "限时活动", "3.png")
    Image.open(a2).save(tmp_path / "2.jpg", quality=90)  # 同一画面重新编码：编码噪声不算变化
    seen = []
    monkeypatch.setattr(vr, "ocr_text", lambda p: seen.append(p.name) or [p.name])
    got = vr.frames_ocr([a, tmp_path / "2.jpg", c, c])
    assert seen == ["1.png", "3.png"] and got == [["1.png"], ["1.png"], ["3.png"], ["3.png"]]


def test_ocr_threads_limited():
    if not vr._load_ocr():
        pytest.skip("没装 rapidocr-onnxruntime")
    import rapidocr_onnxruntime.utils as u
    assert u.SessionOptions().intra_op_num_threads == vr.OCR_THREADS


def test_missing_ocr_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "_OCR", False)
    assert vr.ocr_text(card(tmp_path, "星穹守望")) is None
    content, _ = vr.build_user_content([card(tmp_path, "x")], None, None, 4, "", tmp_path)
    assert "程序识别的图上文字" not in content[1]["text"] and "清晰度" in content[1]["text"]


# ---------- 图片清晰度 ----------

def test_sharpness_drops_when_blurred(tmp_path):
    sharp = vr.image_sharpness(card(tmp_path, "星穹守望", "a.png"))
    soft = vr.image_sharpness(card(tmp_path, "星穹守望", "b.png", blur=6))
    assert soft < sharp / 2


def test_sharpness_of_unreadable_file_is_none(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"not a png")
    assert vr.image_sharpness(p) is None


# ---------- 成片画面统计 ----------

def test_video_blur_measured():
    clean = vr.probe_video(media.video(dur=3))["模糊度"]
    blurred = vr.probe_video(media.video(dur=3, vf="gblur=sigma=6"))["模糊度"]
    assert blurred > clean * 1.5


def test_video_brightness_measured():
    normal = vr.probe_video(media.video(dur=2))["平均亮度(0-255)"]
    dark = vr.probe_video(media.video(dur=2, vf="eq=brightness=-0.42"))["平均亮度(0-255)"]
    assert dark < normal - 50


def test_short_freeze_reported_separately():
    # 0.7 秒冻结低于原来 1 秒的阈值，「冻结帧起点」不报；「短静止」要报出来
    info = vr.probe_video(media.freeze_at(120, 20))
    assert info["冻结帧起点"] == [] and len(info["短静止(0.5–1秒)"]) == 1
    assert float(info["短静止(0.5–1秒)"][0].rstrip("s")) == pytest.approx(4.0, abs=0.25)


def test_long_freeze_not_double_reported():
    info = vr.probe_video(media.freeze_at(120, 45))
    assert len(info["冻结帧起点"]) == 1 and info["短静止(0.5–1秒)"] == []


def test_scene_cuts_detected():
    # 三段不同画面拼接：2 秒、4 秒处是硬切
    p = media.make("cuts.mp4", "-f", "lavfi", "-i", "color=c=red:s=320x180:r=30:d=2",
                   "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=2",
                   "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0", *media.H264)
    cuts = vr.probe_video(p)["场景切换(秒)"]
    assert any(abs(c - 2) <= 0.25 for c in cuts) and any(abs(c - 4) <= 0.25 for c in cuts)


def test_continuous_video_has_no_cuts():
    # testsrc2 是连续运动的测试图，没有硬切
    assert vr.probe_video(media.video(dur=4))["场景切换(秒)"] == []


# ---------- 抽帧时间表 ----------

def test_scene_frames_added_after_cut():
    times, _ = vr.frame_times(30, 4, scenes=[12.0])
    assert 12.1 in times


def test_gap_at_most_one_second_when_under_cap():
    times, _ = vr.frame_times(20, 4)
    later = [t for t in times if t >= 2.5]
    assert len(times) < vr.MAX_FRAMES and max(b - a for a, b in zip(later, later[1:])) <= vr.MAX_GAP + 0.01


@pytest.mark.parametrize("duration", [60, 120, 600])
def test_long_videos_capped(duration):
    times, tail = vr.frame_times(duration, 12, scenes=[float(s) for s in range(4, duration, 2)])
    assert len(times) == vr.MAX_FRAMES and tail in times and {0, 0.5, 1, 1.5, 2, 2.5} <= set(times)


def test_zero_n_means_hook_and_tail_only():
    times, _ = vr.frame_times(10, 0, scenes=[5.0])
    assert times == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 5.1, 9.9]


# ---------- 及格线附近转人审 ----------

def creative_run(rubric, total):
    """总分恰好为 total 的创意采样（每维同分）。"""
    return make_run(rubric, "creative", [total] * 8)


@pytest.mark.parametrize("score,flag", [(2, False), (3, True), (4, False)])
def test_borderline_total_flagged(rubric, score, flag):
    r = vr.aggregate("creative", rubric, [creative_run(rubric, score)])
    assert (vr.BORDERLINE_REVIEW in r["needs_human_review"]) is flag


def test_borderline_edges_inclusive(rubric):
    # 总分 2.8：C1(0.2)=2，其余 3 → 0.2*2+0.8*3 = 2.8
    r = vr.aggregate("creative", rubric, [make_run(rubric, "creative", [2] + [3] * 7)])
    assert r["total"] == 2.8 and vr.BORDERLINE_REVIEW in r["needs_human_review"]


def test_borderline_not_flagged_for_redline_reject(rubric):
    r = vr.aggregate("creative", rubric, [make_run(rubric, "creative", [3] * 8, hits=("R1",))])
    assert vr.BORDERLINE_REVIEW not in r["needs_human_review"]


def test_borderline_range_configurable(rubric):
    rb = {**rubric, "verdict_rules": {**rubric["verdict_rules"], "borderline": {"total": [3.9, 4.1]}}}
    r = vr.aggregate("creative", rb, [creative_run(rubric, 4)])
    assert vr.BORDERLINE_REVIEW in r["needs_human_review"]


# ---------- 判断细则进提示词 ----------

@pytest.mark.parametrize("stage", ["creative", "storyboard", "asset", "video"])
def test_judging_rules_in_both_prompts(rubric, stage):
    assert vr.JUDGING_RULES in vr.build_system_prompt(stage, rubric)
    for panel in vr.stage_panels(stage, rubric):
        assert vr.JUDGING_RULES in vr.build_system_prompt(stage, rubric, panel)


@pytest.mark.parametrize("phrase", ["只依据关键帧", "逐字比对", "站外引流", "公益提醒", "篇幅", "不算冻结帧", "不能以「可能是 OCR 误识」为由不判", "红线归属看行为性质", "在正常范围内就不要因测量值扣分"])
def test_judging_rules_cover_report_findings(phrase):
    assert phrase in vr.JUDGING_RULES
