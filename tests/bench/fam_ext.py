"""e1 感知质量与人一致、e2 审美偏序（DESIGN_v4 §2）。公开数据集在 VR_BENCH_EXT（ext_import.py 下载）。

e1：单张图 / 单个短片作为一次资产 / 成片评审送入，只看 A2（及 A5）、V3（及 V2、V6）与人工评分的 Spearman 相关。
    不给品牌规范和分镜，评审说明写明这一点；其余维度不参与计算。
e2：同一素材的好版 / 差版，只要求方向。好版尽量复用 e1 的用例，不重复调用。
"""
import json

import build_dataset as bd  # noqa: E402
import exemplars as ex
import inject as ij
from common import EXT
from v2lib import SCS, TEST, better, corr, main_id, mut, render_video

ASSET_NOTE = ("# 评审说明\n\n本次只评审一张候选图片，用于判断能否作为广告素材使用。没有分镜与品牌规范，"
              "相关维度请写明「材料未提供」；请重点评审技术规格与视觉质量（清晰度、曝光、构图、瑕疵）。\n")
VIDEO_NOTE = ("# 评审说明\n\n本次只评审一段 AI 生成的候选短片素材（无声，约 3 秒），用于判断能否剪进广告。"
              "没有分镜与台词，相关维度请写明「材料未提供」；请重点评审画面质量、动作是否连贯、与生成提示词是否一致。\n")
VIDEO_HINT = "网页信息流横屏素材位，{w}x{h}，单段素材 3 秒，静音自动播放"


def manifest():
    p = EXT / "manifest.json"
    if not p.exists():
        raise SystemExit(f"缺少 {p}：先运行 tests/bench/ext_import.py")
    return json.loads(p.read_text(encoding="utf-8"))["items"]


def asset_list(item, size, name=None):
    if item["source"] == "koniq":
        row = f"| {name or '候选图片'} | 图片 | {size[0]}x{size[1]} JPG | 图库采购 | 已购买商用授权（编号 LIC-STOCK-{item['id'][-6:]}） |"
    else:
        row = (f"| {name or '候选图片'} | AI 生成图片 | {size[0]}x{size[1]} PNG | 自部署文生图模型生成，提示词：{item['prompt']} | "
               f"自有生成结果，可商用 |")
    return "# 候选素材清单\n\n| 资产 | 类型 | 规格 | 来源 | 授权 |\n|---|---|---|---|---|\n" + row + "\n"


def image_case(b, cid, item, img=None):
    """img：替换后的图（e2 差版）；缺省用原图。"""
    from PIL import Image
    src = EXT / item["file"][4:]
    ext = src.suffix
    if img is None:
        f = item["file"]
        size = Image.open(src).size
    else:
        f = b.image(cid, f"candidate{ext}", img)
        size = img.size
    note = b.text(cid, "评审说明.md", ASSET_NOTE)
    return {"files": [f, b.text(cid, "素材清单.md", asset_list(item, size))], "context": [note]}


def video_case(b, cid, item, make=None):
    f = b.media(cid, "clip.mp4", make) if make else item["file"]
    w, h = ij.video_size(EXT / item["file"][4:])
    note = b.text(cid, "评审说明.md", VIDEO_NOTE + f"\n生成提示词：{item['prompt']}\n")
    return {"files": [f], "context": [note], "platform_hint": VIDEO_HINT.format(w=w, h=h)}


def e1_id(item):
    return f"e1_{item['id']}"


def e1(b):
    for it in manifest():
        if it["source"] == "irdb" and not it.get("in_e1"):
            continue
        cid = e1_id(it)
        if it["source"] == "koniq":
            chks = [corr("e1.srcc/A2_koniq", ["A2"], it["scores"]["MOS"])]
            stage, inp = "asset", image_case(b, cid, it)
        elif it["source"] == "irdb":
            chks = [corr("e1.srcc/A2_aigc", ["A2"], it["scores"]["fidelity"]),
                    corr("e1.srcc/A5_align", ["A5"], it["scores"]["alignment"], report=True)]
            stage, inp = "asset", image_case(b, cid, it)
        else:
            s = it["scores"]
            chks = [corr("e1.srcc/V3_aigc", ["V3"], s["visual"]), corr("e1.srcc/V2_temporal", ["V2"], s["temporal"], report=True),
                    corr("e1.srcc/V6_align", ["V6"], s["alignment"], report=True)]
            stage, inp = "video", video_case(b, cid, it)
        b.add(cid, "e1", it["source"], stage, None, inp, chks, f"公开数据集 {it['source']}：{it['scores']}",
              source=f"公开数据集人工评分（{it['source']}）", ext_id=it["id"], truth=it["scores"])


IMG_BAD = {"cut": lambda im: ij.cut_subject(im), "occlude": lambda im: ij.occlude(im),
           "cast": lambda im: ij.color_cast(im), "clutter": lambda im: ij.clutter(im, n=60),
           "overexpose": lambda im: ij.exposure(im, 1.3)}


def e2(b):
    from PIL import Image
    items = manifest()
    # 图片：ImageRewardDB 同一提示词下人工评分高 / 低的天然一对
    pairs = {}
    for it in items:
        if it.get("pair"):
            pairs.setdefault(it["pair"], {})[it["pair_role"]] = it
    for pid, pr in sorted(pairs.items()):
        ids, new = {}, []
        for role, it in sorted(pr.items()):
            cid = e1_id(it) if it.get("in_e1") else f"e2_{it['id']}"
            if not it.get("in_e1"):
                b.add(cid, "e2", "image.natural", "asset", None, image_case(b, cid, it), [], f"天然偏序对 {pid} 的 {role}",
                      source="公开数据集人工评分（irdb）", ext_id=it["id"], truth=it["scores"])
                new.append(b.labels[-1])
            ids[role] = cid
        if new:  # 两张都已在 e1 里时没有 e2 用例可挂，这一对只在 e1 里用
            new[-1]["checks"] = [better("e2.pair_order/image", ["A2"], ids["hi"], ids["lo"]),
                                 better("e2.total_order/image", "total", ids["hi"], ids["lo"])]
    # 图片：KonIQ 高分图上构造差版（只在完整集：构造方向是我定的，天然偏序对更可信）
    top = [] if not b.full else sorted((it for it in items if it["source"] == "koniq"), key=lambda it: -it["scores"]["MOS"])[:8]
    for it in top:
        im = Image.open(EXT / it["file"][4:]).convert("RGB")
        for g, fn in IMG_BAD.items():
            cid = f"e2_{it['id']}_{g}"
            b.add(cid, "e2", f"image.{g}", "asset", None, image_case(b, cid, it, fn(im)),
                  [better("e2.pair_order/image", ["A2"], e1_id(it), cid), better("e2.total_order/image", "total", e1_id(it), cid)],
                  f"KonIQ 高分图（MOS {it['scores']['MOS']}）的差版：{g}", source="构造", ext_id=it["id"])
    # 成片：主集基准与 VideoFeedback 高分片的差版
    vf_top = sorted((it for it in items if it["source"] == "vf"), key=lambda it: -it["scores"]["visual"])[:6]
    for it in vf_top:
        src = EXT / it["file"][4:]
        for g, fn in (("shake", ij.shake), ("dark", ij.underexpose)):
            cid = f"e2_{it['id']}_{g}"
            b.add(cid, "e2", f"video.{g}", "video", None, video_case(b, cid, it, make=lambda dst, fn=fn, src=src: fn(src, dst)),
                  [better("e2.pair_order/video", ["V3"], e1_id(it), cid), better("e2.total_order/video", "total", e1_id(it), cid)],
                  f"VideoFeedback 高分片的差版：{g}", source="构造", ext_id=it["id"])
    for sid in TEST:
        sc = SCS[sid]
        src = b.video_base(sid)
        good = main_id(sid, "video")

        def dead_air(dst):
            segs = bd.video_segments(sc, tuple(sc["platform"]["size"]), ai_label=sc["ai_generated"])
            segs[2]["dur"] += 4
            render_video(sc, dst, segments=segs)
        for g, make, dim in (("shake", lambda dst: ij.shake(src, dst), "V3"), ("dark", lambda dst: ij.underexpose(src, dst), "V3"),
                             ("dead_air", dead_air, "V2")):
            cid = f"e2_{sid}_v_{g}"
            b.add(cid, "e2", f"video.{g}", "video", sc, b.video_case(cid, sid, make=make),
                  [better("e2.pair_order/video", [dim], good, cid), better("e2.total_order/video", "total", good, cid)],
                  {"shake": "全片手持抖动", "dark": "全片欠曝", "dead_air": "镜 3 拖长 4 秒（同一画面，节奏拖沓）"}[g], base=good)
    # 分镜：首次附 AI 生成提示词的好坏（只在完整集）
    for sid in (TEST if b.full else ()):
        sc = SCS[sid]
        exs = ex.apply(sc)
        good = f"b17_{sid}_storyboard_exemplar"
        bads = {"prompt_vague": lambda s: [x.update({"prompt": "高质量，电影感，4K" if not x["prompt"].startswith(("实拍", "录屏", "游戏实机", "MG"))
                                                    else x["prompt"]}) for x in s["storyboard"]],
                "prompt_conflict": rotate_prompts}
        for g, fn in bads.items():
            cid = f"e2_{sid}_sb_{g}"
            b.add(cid, "e2", f"storyboard.{g}", "storyboard", sc, b.storyboard_case(cid, mut(exs, fn), ctx_sc=exs),
                  [better("e2.pair_order/storyboard", ["S7"], good, cid), better("e2.total_order/storyboard", "total", good, cid)],
                  {"prompt_vague": "AI 镜头的提示词只剩「高质量，电影感，4K」", "prompt_conflict": "提示词整体错位两镜，与镜头描述矛盾"}[g],
                  base=good)


def rotate_prompts(s):
    """提示词整体后移两镜：每镜的提示词描述的是别的镜头。"""
    ps = [x["prompt"] for x in s["storyboard"]]
    k = 2 % len(ps)
    for x, p in zip(s["storyboard"], ps[-k:] + ps[:-k]):
        x["prompt"] = p
