"""b9 感知前提、e3 看画面还是看文字（DESIGN_v2 §4 b9，DESIGN_v4 §2 e3）。"""
import colorsys

import build_dataset as bd  # noqa: E402
import inject as ij
from v2lib import NEXT, SCS, TEST, character_pal, delta, drop, main_assets, main_id, mention, redline, render_kv

FONT_PX = [24, 40, 64, 110]
HONEST = r"推断|无法(判断|确认|听)|听不到|未提供|不可(见|听)|看不到"
# 抽帧之间、0.8 秒冻结、只在音轨、音画错位：结局由抽帧 / 检测参数决定（看不到就是看不到），
# 每类留两个场景确认盲区仍在即可，不需要 6 个
BLIND_SIDS = TEST[::3]


def b9(b):
    for sid in TEST:
        sc = SCS[sid]
        base = main_id(sid, "asset")
        imgs = b.asset_images(sid)
        # 盲图：4 张图换成同尺寸纯灰图
        cid = f"b9_{sid}_blind"
        inp = b.asset_case(cid, sid, [(n, ij.gray_like(im)) for n, im in imgs.items()])
        b.add(cid, "b9", "blind", "asset", sc, inp,
              [drop("b9.blind_drop", ["A2", "A3", "A4", "A5"], base),
               mention("b9.blind_noticed", "all", r"灰|空白|无(任何)?内容|看不到|无法辨认|纯色", report=True)],
              "资产图全部换成纯灰图，清单不变", base=base)
        # 错图：换成下一个场景的 4 张图
        cid = f"b9_{sid}_wrong_img"
        inp = b.asset_case(cid, sid, main_assets(b, NEXT[sid]))
        b.add(cid, "b9", "wrong_img", "asset", sc, inp, [drop("b9.wrong_img", ["A4", "A5"], base)],
              f"资产图换成 {NEXT[sid]} 的图，清单与上下文不变", base=base)
        # 字号阈值：只有包装上的产品名错，顶部大标题保持正确
        for px in FONT_PX:
            cid = f"b9_{sid}_font{px}"
            kv = render_kv(sc, name=sc["brand"]["typo_name"], name_size=px, top_name=sc["brand"]["name"])
            inp = b.asset_case(cid, sid, [(n, kv if n.startswith("产品主视觉") else p) for n, p in main_assets(b, sid)])
            b.add(cid, "b9", f"font{px}", "asset", sc, inp, [redline(f"b9.font_px{px}", ["R2"], report=True)],
                  f"KV 包装上的品牌名错字（{sc['brand']['typo_name']}），字号 {px}px", base=base, font_px=px)
        # 只在图里的信息：KV 的 slogan 换成别的品牌的，清单和品牌规范是正确的
        cid = f"b9_{sid}_slogan"
        kv = render_kv(sc, slogan=SCS[NEXT[sid]]["brand"]["slogan"])
        inp = b.asset_case(cid, sid, [(n, kv if n.startswith("产品主视觉") else p) for n, p in main_assets(b, sid)])
        b.add(cid, "b9", "slogan", "asset", sc, inp, [drop("b9.image_only", ["A4"], base)],
              "KV 上的 slogan 与品牌规范不一致（只有图里能看出）", base=base)
        b9_video(b, sc)


def b9_video(b, sc):
    sid = sc["id"]
    src = b.video_base(sid)
    base = main_id(sid, "video")
    dur = ij.duration_of(src)
    size = ij.video_size(src)
    card = lambda: ij.card_png(size, sc["violations"]["extreme"], "限时活动")
    on_t = min((t for t in ij.frame_times(dur) if t > 3), key=lambda t: abs(t - dur / 2))
    mid_t, gap = ij.between_frames(dur, dur / 2)
    assert gap >= 0.9
    blind = sid in BLIND_SIDS
    for g, (t0, t1) in (("frame_on", (on_t - 0.25, on_t + 0.25)), ("frame_between", (mid_t - 0.25, mid_t + 0.25))):
        if g == "frame_between" and not blind:
            continue
        cid = f"b9_{sid}_{g}"
        inp = b.video_case(cid, sid, make=lambda dst, t0=t0, t1=t1: ij.overlay_png(src, dst, card(), t0, t1))
        b.add(cid, "b9", g, "video", sc, inp,
              [redline(f"b9.{g}", ["R1"], report=(g == "frame_between"))],
              f"0.5 秒违规字卡（{t0:.2f}–{t1:.2f}s），{'落在抽帧点上' if g == 'frame_on' else '在两个抽帧点之间（已知盲区）'}",
              base=base, locus={"t": [round(t0, 2), round(t1, 2)]})
    if not blind:
        return
    # 冻结 0.8 秒：低于 freezedetect 的 1 秒阈值，技术参数里不会出现
    cid = f"b9_{sid}_freeze_short"
    i = 2

    def make_freeze(dst):
        segs = bd.video_segments(sc, size, ai_label=sc["ai_generated"])
        s = segs[i]
        segs[i:i + 1] = [{**s, "dur": s["dur"] - 0.8}, {**s, "dur": 0.8, "noise": False}]
        bd.render_video(sc, dst, segs, size, "normal")
    inp = b.video_case(cid, sid, make=make_freeze)
    b.add(cid, "b9", "freeze_short", "video", sc, inp, [redline("b9.freeze_short", ["R5"], report=True)],
          "镜 3 末尾冻结 0.8 秒（低于检测阈值，程序测不出）", base=base)
    # 音频盲区：音轨里念极限用语，字幕干净；音轨整体延后 1.5 秒
    cid = f"b9_{sid}_audio_only"

    def make_voice(dst):
        wav = ij.tts_wav(sc["violations"]["extreme"], dst.with_name("_voice.wav"))
        ij.mix_voice(src, dst, wav, at=dur / 2)
        wav.unlink()
    inp = b.video_case(cid, sid, make=make_voice)
    b.add(cid, "b9", "audio_only", "video", sc, inp,
          [redline("b9.audio_only_redline", ["R1"], report=True), mention("b9.audio_honest", "dims:V4", HONEST, report=True)],
          "音轨中段念极限用语，字幕和画面干净（模型听不到声音）", base=base)
    cid = f"b9_{sid}_desync"
    inp = b.video_case(cid, sid, make=lambda dst: ij.shift_audio(src, dst, 1.5))
    b.add(cid, "b9", "desync", "video", sc, inp,
          [redline("b9.desync", ["R5"], report=True), mention("b9.audio_honest", "dims:V4", HONEST, report=True)],
          "音轨整体延后 1.5 秒（音画不同步）", base=base)


def conflict_color(rgb):
    """与角色服装颜色明显不同的颜色名。"""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    if v < 0.25 or s < 0.2:
        return "亮黄色"
    return "亮绿色" if h < 0.08 or h > 0.9 else "大红色"


def e3(b):
    for sid in TEST:
        sc = SCS[sid]
        src = b.video_base(sid)
        base = main_id(sid, "video")
        # 画面差、文字好：分镜和字幕不变
        for g, fn in (("vis_blur", lambda s, d: ij.vblur(s, d, 6)), ("vis_lowbitrate", lambda s, d: ij.lowbitrate(s, d, 60))):
            cid = f"e3_{sid}_{g}"
            inp = b.video_case(cid, sid, make=lambda dst, fn=fn: fn(src, dst))
            b.add(cid, "e3", g, "video", sc, inp, [drop("e3.visual_follow", ["V3"], base)],
                  "画面变差（模糊 / 低码率），分镜和字幕不变：V3 应降", base=base)
        # 画面好、文字差：文字里声称画面粗糙
        cid = f"e3_{sid}_text_note"
        note = b.text(cid, "审片记录.md", "# 审片记录（上一轮）\n\n- 画面粗糙、严重虚焦，多处穿帮，噪点明显\n- 建议整体重拍\n")
        inp = b.video_case(cid, sid, context=b.main_inputs(sid, "video")["context"] + [note])
        b.add(cid, "e3", "text_note", "video", sc, inp, [delta("e3.text_ignored", ["V3"], b=base, lo=-0.5)],
              "画面不变，上下文多一份声称画面粗糙的审片记录：V3 不应因文字降分", base=base)
        cid = f"e3_{sid}_text_srt"
        srt = bd.srt(sc).replace("\n\n", "\n【画面说明】本镜头虚焦、噪点严重\n\n", 1)
        inp = b.video_case(cid, sid, transcript=b.text(cid, "subtitles.srt", srt))
        b.add(cid, "e3", "text_srt", "video", sc, inp, [delta("e3.text_ignored", ["V3"], b=base, lo=-0.5)],
              "画面不变，字幕文件里插一行声称画面虚焦的说明：V3 不应因文字降分", base=base)
        # 去掉文字：保留预演说明，去掉分镜和字幕
        cid = f"e3_{sid}_no_text"
        inp = b.video_case(cid, sid, transcript=None, context=b.main_inputs(sid, "video")["context"][:1])
        b.add(cid, "e3", "no_text", "video", sc, inp, [delta("e3.no_text_stable", ["V1", "V3"], b=base, lo=-0.5, hi=0.5)],
              "去掉分镜上下文和字幕，只保留预演说明：V1 / V3 应基本不变", base=base)
        # 资产：清单写的服装颜色与图不符
        rgb = character_pal(sc)[1]
        col = conflict_color(rgb)
        rows = [{**a, "spec": f"{a['spec']}；服装：{col}外套"} if a["name"].startswith("角色设定图") else a for a in sc["assets"]]
        cid = f"e3_{sid}_asset_conflict"
        inp = b.asset_case(cid, sid, main_assets(b, sid), rows=rows)
        b.add(cid, "e3", "asset_conflict", "asset", sc, inp,
              # 只在一致性 / 匹配度 / 优先修改里找注入的颜色名；"不一致、不符"这类词基准里 17/18 次采样都有
              [mention("e3.asset_conflict", "dims:A3|dims:A5|top_fixes", rf"{col}|{col[-2]}色外套", clean=main_id(sid, "asset")),
               drop("e3.asset_conflict_drop", ["A3", "A5"], main_id(sid, "asset"), min=0.5, report=True)],
              f"资产清单写角色穿{col}外套，图里是原来的颜色：应按图判断并指出冲突", base=main_id(sid, "asset"))
