"""注入自检：标签由构造决定，所以每种构造本身要可核验（DESIGN_v2 §2"注入自检"）。

纯函数部分随 A 层一起跑；读生成好的第二轮媒体的部分，没生成时跳过：
.venv/Scripts/python -X utf8 -m pytest -c tests/pytest.ini tests/bench/test_inject.py
"""
import json

import pytest
from PIL import Image, ImageChops

import build_dataset as bd  # noqa: E402
import exemplars as ex
import inject as ij
from common import V2, load_v2, resolve
from fam_scale import asset_many, looped, pad_text
from v2lib import SCS, TEST, render_kv

from video_review import extract_frames, probe_video  # noqa: E402

SC = SCS["S04"]


def same(a, b):
    return ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None


def test_render_kv_defaults_match_main_set():
    for sid in ("S03", "S06"):
        sc = SCS[sid]
        assert same(render_kv(sc), bd.render_kv(sc))
        assert same(render_kv(sc, name=sc["brand"]["typo_name"]), bd.render_kv(sc, name=sc["brand"]["typo_name"]))


def test_font_size_variant_changes_only_package_name():
    sc = SC
    good, bad = render_kv(sc), render_kv(sc, name=sc["brand"]["typo_name"], name_size=40, top_name=sc["brand"]["name"])
    box = ImageChops.difference(good, bad).getbbox()
    # 只有包装中部的品牌名那块变了，顶部大标题（H*0.12）和 slogan（H*0.88）不变
    assert box and box[1] > 1920 * 0.3 and box[3] < 1920 * 0.6


def test_image_injections_measurable():
    im = bd.render_kv(SC)
    assert ij.sharpness(ij.blur(im, 6)) < ij.sharpness(im) * 0.5
    assert ij.mean_luma(ij.exposure(im, 1.3)) > ij.mean_luma(im) + 20
    assert abs(((ij.mean_hue_deg(ij.hue_shift(im, 150)) - ij.mean_hue_deg(im) + 180) % 360) - 180) > 90
    for fn in (ij.cut_subject, ij.occlude, lambda x: ij.clutter(x, n=60)):  # e2 用 n=60
        assert ij.diff_ratio(im, fn(im)) > 0.05
    assert ij.diff_ratio(im, ij.gray_like(im)) > 0.5


def test_asset_many_positions_and_rows():
    for n, k in ((12, 0), (12, 5), (12, 11), (28, 27), (4, 3)):
        imgs, rows, kv = asset_many(SC, n, wrong_at=k)
        assert len(imgs) == n and imgs[k][0] == kv and kv.startswith(f"{k + 1:02d}_")
        assert same(imgs[k][1], render_kv(SC, name=SC["brand"]["typo_name"]))
        names = {r["name"] for r in rows}
        assert all(f[:-4] in names for f, _ in imgs)  # 清单逐张列出


def test_pad_text_size_and_not_repetitive():
    for kb in (5, 20, 60):
        t = pad_text(SC, kb * 1024)
        assert kb * 1024 <= len(t.encode("utf-8")) < kb * 1024 + 2048
        lines = [x for x in t.splitlines() if x.strip()]
        assert len(set(lines)) == len(lines)


def test_looped_length_and_black():
    for total in (15, 60, 180):
        segs = looped(SC, total)
        dur = sum(s["dur"] for s in segs)
        assert total - 6 <= dur <= total + 6, (total, dur)
        assert sum(1 for s in segs if s["img"] is None) == 1


def test_exemplars_clean():
    """范例不能带禁用词（否则"应当通过"的标签不成立），且故事核心不变（品牌名、产品、CTA 镜头还在）。"""
    for sid in TEST:
        sc = SCS[sid]
        s = ex.apply(sc)
        text = json.dumps({k: s[k] for k in ("brief", "proposal", "storyboard")}, ensure_ascii=False)
        assert not [w for w in bd.FORBIDDEN if w in text], sid
        assert len(s["storyboard"]) == len(sc["storyboard"]) and s["storyboard"][-1]["sub"] == sc["storyboard"][-1]["sub"]
        assert sum(x["dur"] for x in s["storyboard"]) == sc["platform"]["duration"]


def test_between_frames_really_between(tmp_path):
    """frame_times 与产品 extract_frames 一致；between_frames 选出的时间点离最近的抽帧点 ≥ 0.45 秒。"""
    src = tmp_path / "v.mp4"
    bd.render_video(SC, src, [{"img": bd.render_kv(SC).resize((270, 480)), "dur": 15, "noise": True}], (270, 480), "none")
    dur = ij.duration_of(src)
    got = [t for t, _ in extract_frames(src, dur, 12, tmp_path)]
    assert got == ij.frame_times(dur)
    mid, gap = ij.between_frames(dur, dur / 2)
    assert min(abs(mid - t) for t in got) >= 0.45 and gap >= 0.9


# ---------------- 生成好的媒体（cases_v2.py 之后） ----------------
LABELS = {l["case_id"]: l for l in load_v2()}


def media(cid):
    if cid not in LABELS:
        pytest.skip(f"没有 {cid}")
    p = resolve(LABELS[cid]["inputs"]["files"][0])
    if not p.exists():
        pytest.skip(f"没有 {p}")
    return p


@pytest.mark.parametrize("sid", ["S03", "S06"])
def test_generated_video_defects_measurable(sid):
    base = probe_video(resolve(f"dataset/cases/{sid}_video_base/final.mp4"))
    assert probe_video(media(f"b9_{sid}_freeze_short"))["冻结帧起点"] == [], "0.8 秒冻结应低于检测阈值"
    assert probe_video(media(f"b9_{sid}_desync"))["时长(秒)"] >= base["时长(秒)"] - 0.2
    v = probe_video(media(f"b9_{sid}_audio_only"))
    assert abs(v["综合响度(LUFS)"] - base["综合响度(LUFS)"]) < 1.5, "混入人声后响度应与基准一致（免得 V4 因响度降分）"
    assert not probe_video(media(f"b9_{sid}_frame_on"))["黑帧区间"]


REAL_KEYS = sorted({c.split("_")[1] for c in LABELS if c.startswith("b10_") and c.endswith("_v_base")})[:2]


@pytest.mark.skipif(not REAL_KEYS, reason="本地没有真实素材子集")
@pytest.mark.parametrize("key", REAL_KEYS)
def test_real_video_defects_measurable(key):
    """真实成片注入：黑场测得出、响度降到 -30 以下、其余变体没有意外引入黑场。"""
    base = probe_video(media(f"b10_{key}_v_base"))
    assert probe_video(media(f"b10_{key}_v_black"))["黑帧区间"] and not base["黑帧区间"]
    assert probe_video(media(f"b10_{key}_v_quiet"))["综合响度(LUFS)"] < -30
    for g in ("extreme", "qr", "lowres", "reencode"):
        if f"b10_{key}_v_{g}" not in LABELS:  # reencode 精简集只在一个项目上有
            continue
        v = probe_video(media(f"b10_{key}_v_{g}"))
        assert not v["黑帧区间"] and abs(v["时长(秒)"] - base["时长(秒)"]) < 0.2, g


@pytest.mark.parametrize("sid", ["S03", "S06"])
def test_generated_card_visible_on_sampled_frame(sid, tmp_path):
    """b9 frame_on 的字卡确实出现在产品会抽到的那一帧上；frame_between 的字卡不在任何抽帧上。"""
    base = resolve(f"dataset/cases/{sid}_video_base/final.mp4")
    for g, expect_seen in (("frame_on", True), ("frame_between", False)):
        p = media(f"b9_{sid}_{g}")
        dur = ij.duration_of(p)
        (tmp_path / g).mkdir()
        (tmp_path / (g + "_b")).mkdir()
        a = dict(extract_frames(p, dur, 12, tmp_path / g))
        b = dict(extract_frames(base, dur, 12, tmp_path / (g + "_b")))
        seen = any(ij.diff_ratio(Image.open(a[t]), Image.open(b[t]), thresh=40) > 0.2 for t in a if t in b)
        assert seen == expect_seen, g


def test_kv_sub_variant_changes_only_package_line():
    for sid in TEST:
        box = ImageChops.difference(render_kv(SCS[sid]), render_kv(SCS[sid], sub="错误型号")).getbbox()
        assert box and box[1] > 1920 * 0.45 and box[3] < 1920 * 0.55, sid


def first_frame(p, tmp, t=0.5):
    tmp.mkdir(exist_ok=True)
    out = tmp / f"{p.parent.name}.png"
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(p), "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


@pytest.mark.parametrize("sid", ["S03", "S05"])
def test_coverage_video_defects_measurable(sid, tmp_path):
    """b25：拖沓版更长、删镜版更短；品牌后置版开头没有角标；R2 版开头没有 AI 标识（左上角与基准不同）。"""
    sc = SCS[sid]
    base_p = resolve(f"dataset/cases/{sid}_video_base/final.mp4")
    dur = ij.duration_of(base_p)
    assert ij.duration_of(media(f"b25_{sid}_V2_drag")) > dur * 1.5
    assert ij.duration_of(media(f"b25_{sid}_V6_cut")) < dur - 1
    w, h = tuple(sc["platform"]["size"])
    base = first_frame(base_p, tmp_path / "b")
    corner = lambda im, right: im.crop((int(w * 0.6), 0, w, int(h * 0.08)) if right else (0, 0, int(w * 0.3), int(h * 0.08)))
    late = first_frame(media(f"b25_{sid}_V5_brand_late"), tmp_path / "l")
    assert ij.diff_ratio(corner(late, True), corner(base, True), thresh=40) > 0.05, "品牌后置版开头不应有品牌角标"
    assert sc["ai_generated"]
    for g in ("end_only", "mid_only"):
        im = first_frame(media(f"b25_{sid}_v_R2_{g}"), tmp_path / g)
        assert ij.diff_ratio(corner(im, False), corner(base, False), thresh=40) > 0.05, f"{g} 开头不应有 AI 标识"

