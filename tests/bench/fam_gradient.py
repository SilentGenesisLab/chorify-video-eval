"""b12 维度梯度（DESIGN_v2 §4 b12 + DESIGN_v3 §3 的向上点）。

每个维度一条序列：[范例（只有 C3/S3 有）, 基准, 轻, 中, 重]，"重"或"中"能复用主集已有变体的直接引用主集用例，不重复调用。
score_v2 对序列算 b12.monotone（相邻两点不升，容差 0.25）；"重"相对基准另判 b12.heavy_drop ≥ 1。
"""
import copy

import build_dataset as bd  # noqa: E402
import inject as ij
from v2lib import SCS, character_pal, drop, main_assets, main_id, mut, render_video, shot_seg

GRAD = ["S03", "S05", "S06", "S08"]


def reorder(s, order):
    s["storyboard"] = [s["storyboard"][i] for i in order]


def drop_mid_shot(s):
    """去掉中间一镜（非钩子、非落版），时长并给前一镜，总时长不变。"""
    m = len(s["storyboard"]) // 2
    s["storyboard"][m - 1]["dur"] += s["storyboard"][m]["dur"]
    s["storyboard"].pop(m)


def lengthen_first(s):
    """镜 1 时长加倍，倒数第二镜相应缩短（至少 1 秒），总时长不变。"""
    k = min(s["storyboard"][0]["dur"], s["storyboard"][-2]["dur"] - 1)
    s["storyboard"][0]["dur"] += k
    s["storyboard"][-2]["dur"] -= k


EMPTY_OPEN = {"size": "全景", "angle": "平视", "move": "缓推", "visual": "空无一人的街道空镜，画面缓慢推进，没有人物和产品",
              "vo": "", "sub": "", "sfx": "环境音", "trans": "硬切", "prompt": "实拍"}

# 维度 → (关卡, [(档, 构造)])；构造是 场景变换函数，或 ("main", 主集变体名)，或 ("img"/"video", 生成函数)
TEXT_LEVELS = {
    "C1": ("creative", [
        ("light", lambda s: s["proposal"].update({"用户洞察": s["proposal"]["用户洞察"] + "；同时希望覆盖 50 岁以上的退休人群"})),
        ("mid", ("main", "cr_offbrief")),
        ("heavy", lambda s: s["proposal"].update({"用户洞察": s["violations"]["offbrief"],
                                                 "故事线": s["violations"]["offbrief"] + "；" + s["proposal"]["故事线"],
                                                 "执行方式": "制作 60 秒横版电视广告，在电视台黄金时段投放"}))]),
    "C3": ("creative", [
        ("light", lambda s: s["proposal"].update({"创意概念": "「改变，从今天开始」"})),
        ("mid", lambda s: s["proposal"].update({"创意概念": "「改变，从今天开始」",
                                               "故事线": f"主角遇到烦恼，朋友推荐了{s['brand']['product']}，使用后问题解决，"
                                                        f"主角露出笑容，结尾出现 Logo"})),
        ("heavy", ("main", "cr_cliche"))]),
    "C4": ("creative", [
        ("light", lambda s: s["proposal"].update({"开场钩子": "前 3 秒是城市航拍空镜与片名字幕，第 4 秒进入：" + s["proposal"]["开场钩子"]})),
        ("mid", lambda s: s["proposal"].update({"开场钩子": "前 5 秒是缓慢推进的城市空镜与片名字幕，第 6 秒进入正题"})),
        ("heavy", ("main", "cr_logo_hook"))]),
    "S1": ("storyboard", [
        ("light", lengthen_first),
        ("mid", lambda s: reorder(s, [0, len(s["storyboard"]) - 2] + list(range(1, len(s["storyboard"]) - 2)) + [len(s["storyboard"]) - 1])),
        ("heavy", lambda s: reorder(s, list(range(len(s["storyboard"])))[::-1]))]),
    "S3": ("storyboard", [
        ("light", lambda s: s["storyboard"][2].update({"visual": s["storyboard"][2]["visual"] + "（上一镜主角手里的黑色手机，这一镜变成了粉色手机）"})),
        ("mid", lambda s: s["storyboard"][1].update({"visual": s["storyboard"][1]["visual"] + "（同一时刻，主角改穿红色连帽卫衣）"})),
        ("heavy", ("main", "sb_continuity"))]),
    "S5": ("storyboard", [
        ("light", drop_mid_shot),
        ("mid", lambda s: s["storyboard"].__setitem__(0, {**s["storyboard"][0], **EMPTY_OPEN})),
        ("heavy", lambda s: (drop_mid_shot(s), s["storyboard"].__setitem__(0, {**s["storyboard"][0], **EMPTY_OPEN}),
                             s.update({"core_override": "品牌形象展示"})))]),
}


def b12(b):
    for sid in GRAD:
        sc = SCS[sid]
        for dim, (stage, levels) in TEXT_LEVELS.items():
            ids = [main_id(sid, stage)]
            if dim in ("C3", "S3"):
                ids.insert(0, f"b17_{sid}_{stage}_exemplar")  # 向上点：范例由 b17 生成
            for lv, how in levels:
                if isinstance(how, tuple):
                    ids.append(main_id(sid, stage, how[1]))
                    continue
                cid = f"b12_{sid}_{dim}_{lv}"
                s2 = mut(sc, how)
                inp = b.creative_case(cid, s2) if stage == "creative" else b.storyboard_case(cid, s2)
                b.add(cid, "b12", f"{dim}.{lv}", stage, sc, inp, gradient_checks(dim, lv, sid, stage), f"{dim} 梯度 {lv}",
                      base=main_id(sid, stage))
                ids.append(cid)
            b.series[f"b12_{sid}_{dim}"] = {"dims": [dim], "ids": ids, "stage": stage}
        b12_media(b, sc)


def gradient_checks(dim, lv, sid, stage):
    if lv == "heavy":
        return [drop("b12.heavy_drop", [dim], main_id(sid, stage))]
    return [drop(f"b12.{lv}_drop", [dim], main_id(sid, stage), min=0.5, report=True)]


def b12_media(b, sc):
    sid = sc["id"]
    imgs = b.asset_images(sid)
    kv_name = next(n for n in imgs if n.startswith("产品主视觉"))
    side_name = next(n for n in imgs if "侧面" in n)
    hair, shirt, long_ = character_pal(sc)
    alt_shirt = bd.mix(shirt, (40, 90, 200), 0.8)
    media = {
        "A2": ("asset", [("light", {kv_name: ij.blur(imgs[kv_name], 2)}), ("mid", {kv_name: ij.blur(imgs[kv_name], 6)}),
                         ("heavy", "as_blur")]),
        "A3": ("asset", [("light", {side_name: bd.render_character(sc, "侧面", (200, 120, 40), shirt, long_)}),
                         ("mid", {side_name: bd.render_character(sc, "侧面", (200, 120, 40), alt_shirt, long_)}),
                         ("heavy", "as_inconsistent")]),
    }
    for dim, (stage, levels) in media.items():
        ids = [main_id(sid, stage)]
        for lv, how in levels:
            if isinstance(how, str):
                ids.append(main_id(sid, stage, how))
                continue
            cid = f"b12_{sid}_{dim}_{lv}"
            inp = b.asset_case(cid, sid, [(n, how.get(n, p)) for n, p in main_assets(b, sid)])
            b.add(cid, "b12", f"{dim}.{lv}", stage, sc, inp, gradient_checks(dim, lv, sid, stage), f"{dim} 梯度 {lv}",
                  base=main_id(sid, stage))
            ids.append(cid)
        b.series[f"b12_{sid}_{dim}"] = {"dims": [dim], "ids": ids, "stage": stage}
    # V1：开场前插入空镜（1 秒 / 3 秒）；V4：响度降 5 / 11 dB
    src = b.video_base(sid)

    def slow_open(sec):
        def make(dst):
            empty = {**sc["storyboard"][0], **EMPTY_OPEN}
            s2 = copy.deepcopy(sc)
            s2["storyboard"].insert(0, {**empty, "dur": sec})
            segs = [shot_seg(s2, 0)] + bd.video_segments(sc, tuple(sc["platform"]["size"]), ai_label=sc["ai_generated"])
            render_video(sc, dst, segments=segs)
        return make
    video = {"V1": [("light", slow_open(1)), ("mid", slow_open(3)), ("heavy", "v_logo_open")],
             "V4": [("light", lambda dst: ij.gain(src, dst, -5)), ("mid", lambda dst: ij.gain(src, dst, -11)), ("heavy", "v_quiet")]}
    for dim, levels in video.items():
        ids = [main_id(sid, "video")]
        for lv, how in levels:
            if isinstance(how, str):
                ids.append(main_id(sid, "video", how))
                continue
            cid = f"b12_{sid}_{dim}_{lv}"
            b.add(cid, "b12", f"{dim}.{lv}", "video", sc, b.video_case(cid, sid, make=how),
                  gradient_checks(dim, lv, sid, "video"), f"{dim} 梯度 {lv}", base=main_id(sid, "video"))
            ids.append(cid)
        b.series[f"b12_{sid}_{dim}"] = {"dims": [dim], "ids": ids, "stage": "video"}
