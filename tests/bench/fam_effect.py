"""b17 上限与通过可达性（DESIGN_v3）、e4 多缺陷与严重程度、e6 结论的业务正确性（DESIGN_v4）。

范例（exemplars.py）由 Claude 按 anchor_5 撰写，非人工；e6 的"应驳回（多个质量缺陷）"档也是我的判断，报告里写明。
"""
import build_dataset as bd  # noqa: E402
import exemplars as ex
import inject as ij
from v2lib import (SCS, TEST, better, delta, drop, main_assets, main_id, mention, mut, order, render_kv, render_video,
                   verdict, video_ctx, video_with_text)

CR, SB = bd.CREATIVE_OPS, bd.STORYBOARD_OPS
LADDER = ["S04", "S08"]


def ex_id(sid, stage):
    return f"b17_{sid}_{stage}_exemplar"


def render_sc(exs, sc):
    """渲染用的范例场景：保留原场景的 global_note（S06 的风险提示条画在每张卡片底部）。"""
    return {**exs, "global_note": sc.get("global_note")}


def exemplar_case(b, cid, sc, stage, exs, fn=None, images=None, rows=None, video_kw=None, srt_sc=None):
    """在范例上构造一个用例：fn 改场景（文本 / 成片），images 换图（资产），rows 换清单（资产）。"""
    s2 = mut(exs, fn) if fn else exs
    if stage == "creative":
        return b.creative_case(cid, s2)
    if stage == "storyboard":
        return b.storyboard_case(cid, s2, ctx_sc=exs)
    if stage == "asset":
        imgs = [(n, (images or {}).get(n, p)) for n, p in main_assets(b, sc["id"])]
        return b.asset_case(cid, sc["id"], imgs, rows=rows if rows is not None else ex.licensed_rows(sc))
    rs = render_sc(s2, sc)
    return video_with_text(b, cid, rs, srt_sc=srt_sc or rs, context=video_ctx(b, cid, exs),
                           make=lambda dst: render_video(rs, dst, **(video_kw or {})))


def b17(b):
    for sid in TEST:
        sc = SCS[sid]
        exs = ex.apply(sc)
        for stage in ("creative", "storyboard", "asset", "video"):
            cid = ex_id(sid, stage)
            b.add(cid, "b17", "exemplar", stage, sc, exemplar_case(b, cid, sc, stage, exs),
                  # 范例是 Claude 写的，没人确认它够得上"通过"：判不到通过不能直接算产品问题，只报告
                  [verdict("b17.pass_reachable", allow=["通过"], report=True),
                   delta("b17.not_below_base", "total", b=main_id(sid, stage), lo=-0.4)],  # 容差取重跑噪声 p95
                  "范例（按 anchor_5 逐条补强，Claude 撰写）", base=main_id(sid, stage), source="Claude 撰写的范例（非人工）")
        if sid in LADDER and b.full:  # 精简集只留范例本身（通过可达性）
            ladder(b, sc, exs)


def ladder(b, sc, exs):
    sid = sc["id"]
    imgs = b.asset_images(sid)
    kv = next(n for n in imgs if n.startswith("产品主视觉"))
    end = next(n for n in imgs if n.startswith("片尾"))
    n = len(exs["storyboard"])
    rungs = {
        "creative": [("C3", {"fn": CR["cr_cliche"][4]}), ("C5", {"fn": CR["cr_brand_late"][4]}),
                     ("C8", {"fn": CR["cr_infeasible"][4]}), ("C4", {"fn": CR["cr_logo_hook"][4]})],
        "storyboard": [("S2", {"fn": SB["sb_monotone"][4]}), ("S3", {"fn": SB["sb_continuity"][4]}),
                       ("S6", {"fn": SB["sb_wrong_platform"][4]}), ("S7", {"fn": SB["sb_drop_fields"][4]})],
        "asset": [("A1", {"images": {kv: imgs[kv].resize((270, 480))}}),
                  ("A2", {"images": {kv: bd.jpeg_crush(ij.blur(imgs[kv], 14))}}),
                  ("A4", {"images": {end: bd.render_endcard(sc, sc["brand"]["alt_color"], stretch=1.6)}}),
                  ("A6", {"rows": [{**a, "source": "", "license": ""} for a in sc["assets"]]})],
        "video": [("V1", {"video_kw": {"logo_open": True}}),
                  ("V2", {"fn": lambda s: s.update(storyboard=[s["storyboard"][0]] + s["storyboard"][1:n - 1][::-1] + [s["storyboard"][-1]])}),
                  ("V4", {"video_kw": {"audio": "quiet"}}),
                  ("V7", {"video_kw": {"no_cta": True}, "srt_sc": {**exs, "storyboard": exs["storyboard"][:-1]}})],
    }
    for stage, rs in rungs.items():
        for dim, kw in rs:
            cid = f"b17_{sid}_{stage}_ladder_{dim}"
            b.add(cid, "b17", f"ladder.{dim}", stage, sc, exemplar_case(b, cid, sc, stage, exs, **kw),
                  [drop("b17.anchor2_drop", [dim], ex_id(sid, stage), min=1.5),
                   order("b17.ladder_order", [dim], [ex_id(sid, stage), main_id(sid, stage), cid])],
                  f"范例上把 {dim} 改到 anchor_2", base=ex_id(sid, stage))


# ---------------- e6 ----------------
REVISE = {"creative": ("C7", {"fn": CR["cr_no_cta"][4]}), "storyboard": ("S1", {"fn": SB["sb_no_cta"][4]}),
          "asset": ("A3", "inconsistent"), "video": ("V8", {"video_kw": {"typo": True}})}
REJECT_RL = {"creative": {"fn": CR["cr_extreme"][4]}, "storyboard": {"fn": SB["sb_danger"][4]},
             "asset": {"images": "wrong_name"}, "video": {"fn": SB["sb_extreme"][4]}}


def compose(*fns):
    def f(s):
        for fn in fns:
            fn(s)
    return f


def inplace(op_fn):
    """bd 的 op() 返回新场景；这里要原地改：把返回值写回。"""
    def f(s):
        s2 = op_fn(s)
        s.clear()
        s.update(s2)
    return f


def e6(b):
    for i, sid in enumerate(TEST):
        sc = SCS[sid]
        exs = ex.apply(sc)
        imgs = b.asset_images(sid)
        kv = next(n for n in imgs if n.startswith("产品主视觉"))
        side = next(n for n in imgs if "侧面" in n)
        end = next(n for n in imgs if n.startswith("片尾"))
        hair, shirt, long_ = bd.hex_rgb(sc["character"]["hair"]), bd.hex_rgb(sc["character"]["shirt"]), sc["character"]["hair_long"]
        bad_side = bd.render_character(sc, "侧面", (200, 120, 40), bd.mix(shirt, (40, 90, 200), 0.8), not long_)
        for stage in ("creative", "storyboard", "asset", "video"):
            b.tiers[ex_id(sid, stage)] = "pass"
            # 应修改后通过：范例 + 一个中等、可修的缺陷
            dim, kw = REVISE[stage]
            if kw == "inconsistent":
                kw = {"images": {side: bad_side}}
            elif "fn" in kw:
                kw = {**kw, "fn": inplace(kw["fn"])}
            cid = f"e6_{sid}_{stage}_revise"
            b.add(cid, "e6", "revise", stage, sc, exemplar_case(b, cid, sc, stage, exs, **kw),
                  [verdict("e6.revise_not_reject", deny=["驳回", "驳回（命中红线）"], report=True)],
                  f"范例 + 一个中等缺陷（{dim}）：应修改后通过", base=ex_id(sid, stage), source="构造 + Claude 判断档位")
            b.tiers[cid] = "revise"
            # 应驳回：前三个场景用红线，后三个场景用多个严重质量缺陷
            cid = f"e6_{sid}_{stage}_reject"
            if i < 3:
                kw = dict(REJECT_RL[stage])
                if kw.get("images") == "wrong_name":
                    kw = {"images": {kv: render_kv(sc, name=sc["brand"]["typo_name"])}}
                else:
                    kw["fn"] = inplace(kw["fn"])
                desc = "范例 + 红线"
            else:
                kw = {"creative": {"fn": compose(*(inplace(CR[v][4]) for v in ("cr_offbrief", "cr_logo_hook", "cr_overload")))},
                      "storyboard": {"fn": compose(*(inplace(SB[v][4]) for v in ("sb_contradict", "sb_no_sound", "sb_drop_fields")))},
                      "asset": {"images": {kv: bd.jpeg_crush(ij.blur(imgs[kv], 14)), side: bad_side,
                                           end: bd.render_endcard(sc, sc["brand"]["alt_color"], stretch=1.6)}},
                      "video": {"video_kw": {"audio": "none", "logo_open": True, "no_cta": True},
                                "srt_sc": {**exs, "storyboard": exs["storyboard"][:-1]}}}[stage]
                desc = "范例 + 多个严重质量缺陷"
            b.add(cid, "e6", "reject", stage, sc, exemplar_case(b, cid, sc, stage, exs, **kw),
                  [verdict("e6.reject_not_pass", deny=["通过"])], f"{desc}：应驳回", base=ex_id(sid, stage),
                  source="构造 + Claude 判断档位")
            b.tiers[cid] = "reject"


# ---------------- e4 ----------------
# 只认指向注入内容的专指词（scenarios.json 的 violations.contradict / offbrief）；
# "矛盾、不符、核心信息"这类通用词在未注入的基准里也常出现，不用
SEVERE_SB = {"S03": r"3\s*小时|一次说对", "S04": r"跑车|两座|一个人", "S05": r"烈火|沙漠", "S06": r"全部存款|短期高收益",
             "S07": r"轻薄|透气|吸量", "S08": r"开放式|环境声"}
SEVERE_CR = {"S03": r"幼儿|幼儿园", "S04": r"大学生|校园", "S05": r"中老年|棋牌", "S06": r"退休|老人",
             "S07": r"大学生|宿舍", "S08": r"70\s*岁|助听|老人"}
SEVERE = {"creative": ("cr_offbrief", SEVERE_CR),
          "storyboard": ("sb_contradict", SEVERE_SB),
          "asset": ("as_wrong_name", None),  # 正则按场景的错字品牌名
          "video": ("v_no_audio", r"无音轨|没有(声音|音轨|音频)|无声|静音|缺少音频")}


def one_typo(text):
    for a, z in bd.TYPOS.items():
        if a in text:
            return text.replace(a, z, 1)
    return None


def minor(stage, sc):
    """只含一个轻微缺陷的场景变换 / 资产清单：一处错字或一处规格笔误。"""
    if stage == "creative":
        key = next(k for k in ("行动指引", "故事线", "开场钩子") if one_typo(sc["proposal"][k]))
        return {"fn": lambda s: s["proposal"].update({key: one_typo(s["proposal"][key])})}
    i = next(i for i, x in enumerate(sc["storyboard"]) if one_typo(x["sub"]))
    if stage in ("storyboard", "video"):
        return {"fn": lambda s: s["storyboard"][i].update({"sub": one_typo(s["storyboard"][i]["sub"])})}
    return {"rows": [{**a, "spec": a["spec"].replace("1920", "1902", 1)} if a["name"].startswith("片尾") else a for a in sc["assets"]]}


def e4(b):
    multi = {"creative": [("cr_no_cta", "C7"), ("cr_logo_hook", "C4"), ("cr_overload", "C6")],
             "storyboard": [("sb_monotone", "S2"), ("sb_no_sound", "S4"), ("sb_continuity", "S3")],
             "asset": [("as_blur", "A2"), ("as_inconsistent", "A3"), ("as_brand_off", "A4")],
             "video": [("v_quiet", "V4"), ("v_logo_open", "V1"), ("v_typo", "V8")]}
    for sid in TEST:
        sc = SCS[sid]
        imgs = b.asset_images(sid)
        kv = next(n for n in imgs if n.startswith("产品主视觉"))
        side = next(n for n in imgs if "侧面" in n)
        end = next(n for n in imgs if n.startswith("片尾"))
        hair, shirt, long_ = bd.hex_rgb(sc["character"]["hair"]), bd.hex_rgb(sc["character"]["shirt"]), sc["character"]["hair_long"]
        for stage, defects in multi.items():
            base = main_id(sid, stage)
            cid = f"e4_{sid}_{stage}_multi"
            if not b.full:  # 精简集只留严重程度（combo / minor）
                pass
            elif stage == "creative":
                inp = b.creative_case(cid, mut(sc, compose(*(inplace(CR[v][4]) for v, _ in defects))))
            elif stage == "storyboard":
                inp = b.storyboard_case(cid, mut(sc, compose(*(inplace(SB[v][4]) for v, _ in defects))))
            elif stage == "asset":
                rep = {kv: bd.jpeg_crush(ij.blur(imgs[kv], 14)),
                       side: bd.render_character(sc, "侧面", (200, 120, 40), bd.mix(shirt, (40, 90, 200), 0.8), not long_),
                       end: bd.render_endcard(sc, sc["brand"]["alt_color"], stretch=1.6)}
                inp = b.asset_case(cid, sid, [(n, rep.get(n, p)) for n, p in main_assets(b, sid)])
            else:
                inp = video_with_text(b, cid, sc, make=lambda dst: render_video(sc, dst, audio="quiet", logo_open=True, typo=True))
            chks = []
            for v, d in (defects if b.full else []):
                # 两者只是 e4.multi_recall_drop 的输入，门槛在差值上
                chks += [drop("e4.multi_recall", [d], base, report=True),
                         delta("e4.single_recall", [d], a=base, b=main_id(sid, stage, v), lo=1.0, report=True)]
            if b.full:
                b.add(cid, "e4", f"multi.{stage}", stage, sc, inp, chks, "同时注入：" + "、".join(v for v, _ in defects), base=base)
            # 严重 + 轻微 同时存在；只有轻微
            sev, pat = SEVERE[stage]
            pat = pat[sid] if isinstance(pat, dict) else pat or rf"{sc['brand']['typo_name']}|品牌名.{{0,6}}(错|误)|名称错"
            mk = minor(stage, sc)
            for g in ("combo", "minor"):
                cid = f"e4_{sid}_{stage}_{g}"
                if stage == "asset":
                    rep = {kv: render_kv(sc, name=sc["brand"]["typo_name"])} if g == "combo" else {}
                    inp = b.asset_case(cid, sid, [(n, rep.get(n, p)) for n, p in main_assets(b, sid)], rows=mk["rows"])
                elif stage == "video":
                    s2 = mut(sc, mk["fn"])
                    inp = video_with_text(b, cid, s2, make=lambda dst, s2=s2, g=g: render_video(s2, dst, audio="none" if g == "combo" else "normal"))
                else:
                    fns = [mk["fn"]] + ([inplace((CR if stage == "creative" else SB)[sev][4])] if g == "combo" else [])
                    s2 = mut(sc, compose(*fns))
                    inp = b.creative_case(cid, s2) if stage == "creative" else b.storyboard_case(cid, s2)
                if g == "combo":
                    chks = [mention("e4.severity_first", "top1", pat, clean=main_id(sid, stage))]
                    desc = f"严重缺陷（{sev}）+ 一处轻微缺陷"
                else:
                    chks = [better("e4.severity_total", "total", good=None, bad=main_id(sid, stage, sev))]
                    desc = "只有一处轻微缺陷（与只有严重缺陷的主集用例比总分）"
                b.add(cid, "e4", f"{g}.{stage}", stage, sc, inp, chks, desc, base=main_id(sid, stage))
