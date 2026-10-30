"""B 层修复的证据送达（0 调用）：注入的问题有没有变成送给模型的程序证据。

付费复测只能回答「模型看到证据后判得对不对」；证据有没有到模型面前是确定的，在这里用生成好的 B 层素材逐类核对：
- 资产图上的错字、别家 slogan、博彩域名小字 → OCR 读得出
- 成片 0.5 / 0.9 秒字卡（含原来抽帧盲区里的）→ 落在抽到的帧上，且 OCR 读得出
- 0.8 秒冻结 → 「短静止」报出来；低码率、模糊等不冻结的画面不误报
- 模糊 → 模糊度高于基准（≥1.2 倍）

没有生成素材（cases_v2.py）或真实素材时跳过。真实素材 b10 只核对代表性的一个项目。
"""
import tempfile
from functools import lru_cache

import pytest

from common import load_v2, resolve
from v2lib import NEXT, SCS, TEST

import video_review as vr  # noqa: E402

LABELS = {l["case_id"]: l for l in load_v2()}


def path_of(cid, prefix=None):
    if cid not in LABELS:
        pytest.skip(f"没有 {cid}")
    files = LABELS[cid]["inputs"]["files"]
    rel = next((f for f in files if prefix is None or f.split("/")[-1].startswith(prefix)), None)
    p = resolve(rel) if rel else None
    if p is None or not p.exists():
        pytest.skip(f"没有 {cid} 的素材")
    return p


def words(p):
    return "".join(vr.ocr_text(p) or [])


def squash(s):
    return "".join(ch for ch in s if ch.isalnum()).lower()


@lru_cache(maxsize=None)
def probe(cid):
    return vr.probe_video(path_of(cid))


@lru_cache(maxsize=None)
def frame_words(cid):
    """[(抽帧时间, 该帧 OCR 文字)]，与 build_user_content 的抽帧、OCR 一致。"""
    p, info = path_of(cid), probe(cid)
    tmp = tempfile.mkdtemp()
    shots = vr.extract_frames(p, info.get("时长(秒)", 0), 12, tmp, info.get("场景切换(秒)", ()))
    return [(t, "".join(w or [])) for (t, _), w in zip(shots, vr.frames_ocr([s for _, s in shots]))]


@pytest.fixture(autouse=True)
def need_ocr():
    if not vr._load_ocr():
        pytest.skip("没装 rapidocr-onnxruntime")


# ---------- 资产图 ----------

@pytest.mark.parametrize("px", [24, 40, 64, 110])
@pytest.mark.parametrize("sid", TEST)
def test_typo_on_package_readable(sid, px):
    b = SCS[sid]["brand"]
    w = words(path_of(f"b9_{sid}_font{px}", "产品主视觉"))
    assert b["typo_name"] in w, f"{px}px 的错字「{b['typo_name']}」OCR 没读出：{w[:80]}"


@pytest.mark.parametrize("sid", TEST)
def test_base_kv_has_no_typo(sid):
    b = SCS[sid]["brand"]
    w = words(path_of(f"{sid}_asset_base", "产品主视觉") if f"{sid}_asset_base" in LABELS else
              resolve(f"dataset/cases/{sid}_asset_base/产品主视觉KV.png"))
    assert b["name"] in w and b["typo_name"] not in w


@pytest.mark.parametrize("sid", TEST)
def test_foreign_slogan_readable(sid):
    slogan = SCS[NEXT[sid]]["brand"]["slogan"]
    assert squash(slogan) in squash(words(path_of(f"b9_{sid}_slogan", "产品主视觉")))


@pytest.mark.parametrize("sid", TEST)
def test_gambling_domain_small_text_readable(sid):
    assert "bet88" in words(path_of(f"b11_{sid}_as_R3_implicit", "角色设定_侧面")).lower()


def real_project():
    """真实素材（b10）的第一个有图有片的项目：项目名与错名只在不进 git 的 fam_real.py 里。"""
    try:
        from fam_real import PROJECTS
    except ImportError:
        pytest.skip("没有真实素材生成脚本")
    key = next((k for k, v in PROJECTS.items() if v["images"] and v["video"]), None)
    return key, PROJECTS[key] if key else pytest.skip("没有真实素材项目")


def test_real_wrong_name_readable():
    key, pj = real_project()
    w = words(path_of(f"b10_{key}_as_wrong_name"))
    assert squash(pj["wrong"]) in squash(w), w[:80]


# ---------- 成片字卡 ----------

def card_frames(cid, needle):
    return [t for t, w in frame_words(cid) if squash(needle) in squash(w)]


@pytest.mark.parametrize("g", ["frame_on", "frame_between"])
@pytest.mark.parametrize("sid", TEST)
def test_half_second_card_sampled_and_read(sid, g):
    # frame_between 原来是抽帧盲区；间隔 ≤1 秒后，0.5 秒字卡至少落在一帧上
    cid = f"b9_{sid}_{g}"
    lo, hi = LABELS[cid]["locus"]["t"] if cid in LABELS else pytest.skip(f"没有 {cid}")
    on = [t for t, _ in frame_words(cid) if lo <= t <= hi]
    assert on, f"{lo}–{hi}s 之间没有抽帧"
    assert any("限时活动" in w for t, w in frame_words(cid) if lo <= t <= hi), "字卡在帧上但 OCR 没读出"


@pytest.mark.parametrize("rid,text", [("R3", "晴天"), ("R4", "点赞过万抽送")])
@pytest.mark.parametrize("sid", TEST)
def test_meaning_card_read(sid, rid, text):
    assert card_frames(f"b11_{sid}_v_{rid}_implicit", text)


@pytest.mark.parametrize("variant", ["extreme", "qr"])
def test_real_video_overlay_read(variant):
    key, pj = real_project()
    # 字卡字号按短边算，长句两端会出画：只核对中间一段；二维码核对旁边的微信号
    text = {"extreme": pj["extreme"][3:9], "qr": "vx"}[variant]
    assert card_frames(f"b10_{key}_v_{variant}", text)


# ---------- 成片测量 ----------

@pytest.mark.parametrize("sid", TEST)
def test_short_freeze_reported(sid):
    assert probe(f"b9_{sid}_freeze_short")["短静止(0.5–1秒)"], "0.8 秒冻结没报出"


@pytest.mark.parametrize("sid", TEST)
def test_no_false_freeze_on_degraded_video(sid):
    # 低码率、模糊抹掉了噪点，但画面在动：不能当成冻结（第二轮注入伪影的教训）
    for g in ("vis_lowbitrate", "vis_blur"):
        info = probe(f"e3_{sid}_{g}")
        assert info["冻结帧起点"] == [] and info["短静止(0.5–1秒)"] == [], g


@pytest.mark.parametrize("sid", TEST)
def test_blur_measured_above_base(sid):
    base = vr.probe_video(resolve(f"dataset/cases/{sid}_video_base/final.mp4"))["模糊度"]
    # S06 底图本身偏柔（基准 4.9），σ=6 只抬到 6.0；其余场景约 1.5–1.7 倍
    assert probe(f"e3_{sid}_vis_blur")["模糊度"] > base * 1.2
