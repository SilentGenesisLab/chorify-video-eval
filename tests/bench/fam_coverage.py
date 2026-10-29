"""b25 补覆盖：第一轮和精简集都没有专门打到的维度（A5 / A6 / V2 / V5 / V6），以及用例偏少的两条红线
（成片 R2 AI 标识 4 例、资产 R2 关键信息错误 8 例）。每类 6 个场景，分项 n=6 只报告，门槛设在合并值上。"""
from PIL import ImageDraw

import build_dataset as bd  # noqa: E402
from v2lib import (NEXT, SCS, TEST, asset_ctx, drop, main_assets, main_id, mut, redline, render_kv, render_video,
                   size_of, video_with_text)

# 包装上品牌名下面的型号 / 品类行写错（与品牌规范、Brief 不一致）：R2「关键信息错误，可能误导消费者」
WRONG_SUB = {"S03": "日语 App", "S04": "S9 燃油轿车", "S05": "新版本「沙漠之城」", "S06": "贷款 App", "S07": "日用纸尿裤",
             "S08": "Air 2 有线耳机"}


def b25(b):
    for sid in TEST:
        sc = SCS[sid]
        other = SCS[NEXT[sid]]
        a_base, v_base = main_id(sid, "asset"), main_id(sid, "video")
        # A5 分镜匹配度：资产不变，上下文里的分镜换成另一个场景的（资产对不上分镜）
        cid = f"b25_{sid}_A5_wrong_sb"
        b.add(cid, "b25", "dim.A5", "asset", sc,
              b.asset_case(cid, sid, main_assets(b, sid), context=asset_ctx(b, cid, sc, storyboard=other)),
              [drop("b25.dim_drop/A5", ["A5"], a_base)], f"上下文分镜换成 {other['id']} 的，资产不变", base=a_base)
        # A6 版权与授权：来源保留，授权只写"已授权"，不写范围和期限（anchor_2「授权不明」）
        rows = [{**a, "license": "已授权"} for a in sc["assets"]]
        cid = f"b25_{sid}_A6_vague"
        b.add(cid, "b25", "dim.A6", "asset", sc, b.asset_case(cid, sid, main_assets(b, sid), rows=rows),
              [drop("b25.dim_drop/A6", ["A6"], a_base)], "资产清单授权栏一律只写「已授权」，无范围 / 期限 / 授权方", base=a_base)
        # 资产 R2：包装上的型号 / 品类行写错，品牌名正确
        imgs = main_assets(b, sid)
        kv = render_kv(sc, sub=WRONG_SUB[sid])
        cid = f"b25_{sid}_as_R2_sub"
        b.add(cid, "b25", "asset.R2", "asset", sc,
              b.asset_case(cid, sid, [(n, kv if n.startswith("产品主视觉") else p) for n, p in imgs]),
              [redline("b25.recall/asset.R2", ["R2"], clean=a_base)],
              f"KV 包装上的型号 / 品类写成「{WRONG_SUB[sid]}」（品牌名正确）", base=a_base, locus={"image": "产品主视觉"})
        b25_video(b, sc, v_base)


def b25_video(b, sc, base):
    sid, size, n = sc["id"], size_of(sc), len(sc["storyboard"])
    mid = list(range(1, n - 1))
    # V2 节奏：中间镜头各拉长到 3 倍（拖沓），字幕按新时长
    slow = mut(sc, lambda s: [s["storyboard"][i].update({"dur": s["storyboard"][i]["dur"] * 3}) for i in mid])
    cid = f"b25_{sid}_V2_drag"
    b.add(cid, "b25", "dim.V2", "video", sc, video_with_text(b, cid, slow),
          [drop("b25.dim_drop/V2", ["V2"], base)], "中间镜头各拉长到 3 倍时长，画面不变", base=base)
    # V5 品牌传达：除片尾外的镜头去掉品牌角标、文字里的品牌名换成泛称
    name = sc["brand"]["name"]
    late = mut(sc, lambda s: [s["storyboard"][i].update({k: s["storyboard"][i][k].replace(name, "它") for k in ("visual", "vo", "sub")})
                              for i in range(n - 1)])
    anon = mut(late, lambda s: s["brand"].update({"name": ""}))

    def make_late(dst):
        segs = [{"img": bd.render_shot(anon, i, anon["storyboard"][i], size, sc["ai_generated"]), "dur": late["storyboard"][i]["dur"],
                 "noise": True} for i in range(n - 1)]
        segs.append({"img": bd.render_shot(sc, n - 1, sc["storyboard"][-1], size, sc["ai_generated"]), "dur": sc["storyboard"][-1]["dur"],
                     "noise": True})
        render_video(sc, dst, segs)
    cid = f"b25_{sid}_V5_brand_late"
    b.add(cid, "b25", "dim.V5", "video", sc, video_with_text(b, cid, late, make=make_late),
          [drop("b25.dim_drop/V5", ["V5"], base)], "品牌名和角标只在最后一镜出现", base=base)
    # V6 前序还原：去掉中间一镜（卖点镜），上下文仍是完整分镜
    k = n // 2
    cut = mut(sc, lambda s: s.update({"storyboard": s["storyboard"][:k] + s["storyboard"][k + 1:]}))
    cid = f"b25_{sid}_V6_cut"
    b.add(cid, "b25", "dim.V6", "video", sc, video_with_text(b, cid, cut),
          [drop("b25.dim_drop/V6", ["V6"], base)], f"成片少了分镜第 {k + 1} 镜（{sc['storyboard'][k]['visual'][:20]}…）", base=base)
    # 成片 R2：AI 生成场景，标识不在开头（只在片尾 / 只在中段一镜）；办法要求视频起始画面有显著标识
    if not sc["ai_generated"]:
        return
    for g, keep in (("end_only", {n - 1}), ("mid_only", {k})):
        def make(dst, keep=keep):
            render_video(sc, dst, [{"img": bd.render_shot(sc, i, s, size, i in keep), "dur": s["dur"], "noise": True}
                                   for i, s in enumerate(sc["storyboard"])])
        cid = f"b25_{sid}_v_R2_{g}"
        b.add(cid, "b25", "video.R2", "video", sc, video_with_text(b, cid, sc, make=make),
              [redline("b25.recall/video.R2", ["R2"], clean=base)],
              f"AI 生成标识只出现在第 {min(keep) + 1} 镜，开头没有", base=base)
    # 边界：每镜都有标识但很小、低对比（是否算"显著"有争议，只报告）
    def make_faint(dst):
        segs = []
        for i, s in enumerate(sc["storyboard"]):
            im = bd.render_shot(sc, i, s, size, False)
            d = ImageDraw.Draw(im)
            d.text((size[0] * 0.04, size[1] * 0.02), "AI生成", font=bd.font(bd.FONT_R, max(12, size[1] // 90)), fill=(150, 150, 150))
            segs.append({"img": im, "dur": s["dur"], "noise": True})
        render_video(sc, dst, segs)
    cid = f"b25_{sid}_v_R2_faint"
    b.add(cid, "b25", "video.R2.faint", "video", sc, video_with_text(b, cid, sc, make=make_faint),
          [redline("b25.faint_R2", ["R2"], clean=base, report=True)], "每镜都有 AI 标识，但字很小、灰色低对比", base=base)
