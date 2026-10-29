"""b14 跨关一致性（DESIGN_v2 §4 b14）、b20 条件判断：平台与上下文（DESIGN_v3 §2 b20）。

b14：上游作为 context 不变，只改下游，使两者矛盾；反向对照是"上游有缺陷、下游忠实还原"，还原度不应被扣。
b20：材料逐字不变，只改平台提示或上下文。
"""
import build_dataset as bd  # noqa: E402
import inject as ij
from v2lib import (NEXT, SCS, TEST, asset_ctx, delta, drop, main_assets, main_id, mention, mut, no_rise, render_video,
                   video_ctx, video_with_text)

LANDSCAPE_HINTS = {"bili": "B 站横屏视频，要求 16:9 1920x1080，时长 30 秒，响度参考 -14～-16 LUFS，真峰值 ≤ -1 dBTP",
                   "expo": "展会 LED 大屏循环播放，要求 16:9 1920x1080 25fps，约 80% 时间静音播放，依赖字幕传达信息"}
PORTRAIT_HINTS = {"douyin": "抖音信息流，要求 9:16 1080x1920，时长 30 秒，响度参考 -14～-16 LUFS，真峰值 ≤ -1 dBTP",
                  "channels": "微信视频号，要求 9:16 1080x1920，时长 30 秒，响度参考 -14～-16 LUFS，真峰值 ≤ -1 dBTP"}
SILENT_HINT = "地铁站与商场电子屏，竖屏 9:16 1080x1920，全程静音播放，只能靠画面和字幕传达信息"
MISSING = r"未提供|没有提供|未附|缺少.{0,6}(分镜|上下文|参考|前序)|无法(对照|比对|核对)"


def b14(b):
    for sid in TEST:
        sc = SCS[sid]
        sb_base, v_base = main_id(sid, "storyboard"), main_id(sid, "video")
        last = len(sc["storyboard"]) - 1
        typo = sc["brand"]["typo_name"]
        # 创意 → 分镜：上下文是主集创意，分镜与之矛盾
        sb_ops = {
            "name": ("产品名与创意不一致", lambda s: [x.update({k: x[k].replace(s["brand"]["name"], typo) for k in ("visual", "vo", "sub")})
                                              for x in s["storyboard"]]),
            "cta": ("CTA 与创意不一致", lambda s: s["storyboard"][last].update({"vo": "关注账号，了解更多品牌故事", "sub": "关注账号 · 了解更多"})),
            "duration": ("总时长与创意不一致（翻倍）", lambda s: [x.update({"dur": x["dur"] * 2}) for x in s["storyboard"]]),
        }
        for g, (desc, fn) in sb_ops.items():
            cid = f"b14_{sid}_sb_{g}"
            b.add(cid, "b14", f"creative_storyboard.{g}", "storyboard", sc, b.storyboard_case(cid, mut(sc, fn)),
                  [drop("b14.detect", ["S5"], sb_base)], f"创意 → 分镜：{desc}", base=sb_base)
        # 分镜 → 成片：上下文是主集分镜，成片少一镜 / 换镜序 / CTA 文案不同
        size = tuple(sc["platform"]["size"])

        def video_drop_shot(dst):
            segs = bd.video_segments(sc, size, ai_label=sc["ai_generated"])
            segs[1]["dur"] += segs[2]["dur"]
            segs.pop(2)
            render_video(sc, dst, segments=segs)

        def video_swap(dst):
            segs = bd.video_segments(sc, size, ai_label=sc["ai_generated"])
            segs[1], segs[2] = segs[2], segs[1]
            render_video(sc, dst, segments=segs)
        cta_sc = mut(sc, lambda s: s["storyboard"][last].update({"vo": "关注账号，了解更多品牌故事", "sub": "关注账号 · 了解更多"}))
        v_ops = {"drop_shot": ("成片少了镜 3", video_drop_shot, sc, ["V6"]),
                 "swap": ("成片镜 2、镜 3 顺序对调", video_swap, sc, ["V6", "V2"]),
                 "cta": ("成片 CTA 与分镜不一致", None, cta_sc, ["V6"])}
        for g, (desc, make, srt_sc, dims) in v_ops.items():
            cid = f"b14_{sid}_v_{g}"
            inp = video_with_text(b, cid, srt_sc, make=make)
            b.add(cid, "b14", f"storyboard_video.{g}", "video", sc, inp, [drop("b14.detect", dims[:1], v_base)],
                  f"分镜 → 成片：{desc}", base=v_base)
        # 品牌规范 → 资产：KV 改成别的品牌标准色（色相整体偏移）
        cid = f"b14_{sid}_as_color"
        imgs = b.asset_images(sid)
        kv_name = next(n for n in imgs if n.startswith("产品主视觉"))
        inp = b.asset_case(cid, sid, [(n, ij.hue_shift(imgs[n], 150) if n == kv_name else p) for n, p in main_assets(b, sid)])
        b.add(cid, "b14", "brand_asset.color", "asset", sc, inp, [drop("b14.detect", ["A4"], main_id(sid, "asset"))],
              "品牌规范 → 资产：KV 色相偏移 150°，与标准色不符", base=main_id(sid, "asset"))
        # 忠实还原有缺陷的上游：创意是 Logo 慢开场，分镜 / 成片照做
        logo_sc = mut(sc, lambda s: s["proposal"].update({"开场钩子": "开场 5 秒播放企业 Logo 动画与品牌发展历程介绍，随后进入正片"}))
        logo_sb = mut(sc, lambda s: s["storyboard"].__setitem__(0, {**s["storyboard"][0], "size": "全景", "angle": "正面", "move": "固定",
                                                                    "visual": "白底，品牌 Logo 缓缓浮现，字幕介绍品牌发展历程",
                                                                    "vo": "", "sub": "", "sfx": "轻音乐", "trans": "淡出",
                                                                    "prompt": "logo animation"}))
        cid = f"b14_{sid}_sb_faithful"
        b.add(cid, "b14", "faithful.storyboard", "storyboard", sc, b.storyboard_case(cid, logo_sb, ctx_sc=logo_sc),
              [delta("b14.faithful", ["S5"], b=sb_base, lo=-0.5), drop("b14.faithful_flaw_seen", ["S1"], sb_base, report=True)],
              "创意本身是 Logo 慢开场，分镜忠实还原：S5 不应被扣，弱点应落在 S1", base=sb_base)
        cid = f"b14_{sid}_v_faithful"
        inp = video_with_text(b, cid, logo_sb, context=video_ctx(b, cid, logo_sb),
                              make=lambda dst: render_video(sc, dst, logo_open=True))
        b.add(cid, "b14", "faithful.video", "video", sc, inp,
              [delta("b14.faithful", ["V6"], b=v_base, lo=-0.5), drop("b14.faithful_flaw_seen", ["V1"], v_base, report=True)],
              "分镜本身是 Logo 开场，成片忠实还原：V6 不应被扣，弱点应落在 V1", base=v_base)


def b20(b):
    for sid in TEST:
        sc = SCS[sid]
        v_base = main_id(sid, "video")
        portrait = sc["platform"]["aspect"] == "9:16"
        # 平台反转：同一支片，换两个画幅相反的平台
        for g, hint in (LANDSCAPE_HINTS if portrait else PORTRAIT_HINTS).items():
            cid = f"b20_{sid}_platform_{g}"
            b.add(cid, "b20", f"platform.{g}", "video", sc, b.video_case(cid, sid, hint=hint),
                  [drop("b20.platform_flip", ["V8"], v_base)], f"同一成片，平台提示改为画幅相反的「{hint[:12]}」", base=v_base)
        # 静音平台：无字幕版本在静音提示下应比有字幕版本更差
        nosub = mut(sc, lambda s: [x.update({"sub": ""}) for x in s["storyboard"]])
        cid_ns = f"b20_{sid}_nosub"
        # 台词稿只含旁白 / 同期声（字幕列为空），否则模型会从"字幕文本"推断画面上有字幕
        b.add(cid_ns, "b20", "silent.nosub", "video", sc, video_with_text(b, cid_ns, nosub),
              [], "画面无字幕（只提供旁白台词稿），默认平台提示", base=v_base)
        cid = f"b20_{sid}_nosub_silent"
        b.add(cid, "b20", "silent.nosub_silent", "video", sc,
              {**b.labels[-1]["inputs"], "platform_hint": SILENT_HINT},
              [drop("b20.silent_nosub", ["V5", "V8"], cid_ns, min=0.5)], "无字幕版本 + 静音播放平台提示", base=cid_ns)
        cid = f"b20_{sid}_sub_silent"
        b.add(cid, "b20", "silent.sub_silent", "video", sc, b.video_case(cid, sid, hint=SILENT_HINT),
              [no_rise("b20.silent_sub_ok", "total", v_base, max=0.3, report=True)], "有字幕原片 + 静音播放平台提示", base=v_base)
    # 上下文消融与张冠李戴：分镜 / 资产 / 成片各 4 个场景
    for sid in TEST[:4]:
        sc = SCS[sid]
        other = SCS[NEXT[sid]]
        for stage, dim in (("storyboard", "S5"), ("asset", "A5"), ("video", "V6")):
            base = main_id(sid, stage)
            for g in ("no_ctx", "wrong_ctx"):
                cid = f"b20_{sid}_{stage}_{g}"
                if stage == "storyboard":
                    inp = b.storyboard_case(cid, sc, ctx=[]) if g == "no_ctx" else b.storyboard_case(cid, sc, ctx_sc=other)
                elif stage == "asset":
                    ctx = asset_ctx(b, cid, sc, storyboard=False) if g == "no_ctx" else asset_ctx(b, cid, sc, storyboard=other)
                    inp = b.asset_case(cid, sid, main_assets(b, sid), context=ctx)
                else:
                    ctx = b.main_inputs(sid, "video")["context"][:1] + ([] if g == "no_ctx" else video_ctx(b, cid, other, note=False))
                    inp = b.video_case(cid, sid, context=ctx)
                if g == "no_ctx":
                    chk = [mention("b20.no_context_honest", f"dims:{dim}", MISSING), no_rise("b20.no_context_no_rise", [dim], base, max=0.0)]
                else:
                    chk = [drop("b20.wrong_context", [dim], base)]
                b.add(cid, "b20", f"context.{stage}.{g}", stage, sc, inp, chk,
                      f"{stage} {'去掉上游上下文' if g == 'no_ctx' else '上下文换成 ' + NEXT[sid] + ' 的'}", base=base)
