#!/usr/bin/env python3
"""构建评审基准数据集：基准样本 + 定向注入缺陷的变体，标签由构造方式确定。

python build_dataset.py [--stages creative storyboard asset video] [--scenarios S01 S02]
输出：dataset/cases/<case_id>/…  与  dataset/labels.jsonl
"""
import argparse
import copy
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from video_review import ffmpeg_exe  # noqa: E402

OUT = HERE / "dataset"
FONT_R = str(ROOT / "assets_lib" / "NotoSansSC-Regular.otf")
FONT_B = str(ROOT / "assets_lib" / "NotoSansSC-Bold.otf")
FPS = 25
DEV_SCENARIOS = {"S01", "S02"}  # 开发集：用于调 rubric；其余为测试集，只用于报告

# 基准样本中不允许出现的用语（保证基准样本"干净"，红线标签才可靠）
FORBIDDEN = ["最佳", "最强", "最好", "最高", "第一", "顶级", "100%", "唯一", "首选", "国家级", "绝对", "稳赚", "保证", "治疗"]

FLUFF = ("【创作说明】本方案始终坚持以用户为中心、以品牌为核心的创作理念，深度融合品牌调性与用户需求，"
         "通过精心打磨的视听语言与情感化的叙事方式，全方位、多维度地传递品牌价值。团队在创作过程中进行了充分的讨论与推敲，"
         "力求在每一个细节上都做到精益求精，兼顾艺术性与商业性，实现品效合一。我们相信，这支作品将以真诚打动人心，"
         "以创意赢得关注，以品质建立信任，为品牌带来持续而深远的影响，助力品牌在激烈的市场竞争中脱颖而出，"
         "实现品牌声量与销售转化的双重增长。")
GENERIC_INSIGHT = "现代人生活节奏越来越快，大家都希望生活变得更美好，追求更高品质的生活。"
TYPOS = {"点击": "点及", "下方": "下放", "购买": "购卖", "体验": "休验", "降噪": "降燥", "预约": "预药", "搜索": "搜锁",
         "防晒": "防哂", "免费": "免废", "限定": "限锭", "腻感": "腻敢", "解除": "解厨", "定投": "定头", "试用": "试拥",
         "新品": "新晶", "清单": "清丹", "外婆": "外波", "电梯": "电涕", "开口": "开扣", "版本": "版夲", "存下": "存吓"}

# ---------------- 文本渲染 ----------------

def md_creative(sc, prose=False, fluff=False):
    b, p = sc["brief"], sc["proposal"]
    L = [f"# {sc['brand']['product']} · 创意提案", "", "## 一、创意 Brief（客户提供）", ""]
    L += [f"- **{k}**：{v}" for k, v in b.items()]
    L += ["", "## 二、创意提案", ""]
    if prose:
        L.append("".join(f"{k}方面，{v}。" for k, v in p.items()))
    else:
        L += [f"- **{k}**：{v}" for k, v in p.items()]
    if fluff:
        L += ["", FLUFF]
    return "\n".join(L) + "\n"


def sb_header(sc):
    pf = sc["platform"]
    total = sum(s["dur"] for s in sc["storyboard"])
    L = [f"# {sc['brand']['product']} · 分镜脚本", "",
         f"- 投放平台：{pf['name']}　画幅：{sc.get('aspect_override', pf['aspect'])}　总时长：{total:g} 秒",
         f"- 核心信息：{sc.get('core_override', sc['brief']['核心信息'])}",
         f"- 制作方式：{'AI 生成为主' if sc['ai_generated'] else '实拍'}（{sc['proposal']['执行方式']}）"]
    if sc.get("global_note"):
        L.append(f"- {sc['global_note']}")
    return L


def md_storyboard(sc, prose=False, fluff=False):
    L = sb_header(sc) + [""]
    cols = ["镜号", "时长", "景别", "角度", "运镜", "画面描述", "台词/旁白", "字幕", "音乐音效", "转场", "AI 提示词/制作"]
    keys = ["dur", "size", "angle", "move", "visual", "vo", "sub", "sfx", "trans", "prompt"]
    if prose:
        for i, s in enumerate(sc["storyboard"], 1):
            parts = [f"{c}：{s[k]:g} 秒" if k == "dur" else f"{c}：{s[k]}" for c, k in zip(cols[1:], keys) if s[k] != ""]
            L.append(f"**镜 {i}**　" + "；".join(parts) + "。")
            L.append("")
    else:
        L += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for i, s in enumerate(sc["storyboard"], 1):
            cells = [str(i)] + [f"{s['dur']:g}s" if k == "dur" else str(s[k]) for k in keys]
            L.append("| " + " | ".join(cells) + " |")
    if fluff:
        L += ["", FLUFF]
    return "\n".join(L) + "\n"


def md_brand(sc):
    b = sc["brand"]
    return (f"# {b['name']} 品牌规范（摘要）\n\n- 品牌名：{b['name']}\n- 产品：{b['product']}\n"
            f"- 标准色：{b['color_name']} {b['color']}\n- 指定字体：思源黑体 Bold（标题）/ Regular（正文）\n"
            f"- Logo：品牌名文字标，标准色，等比使用，禁止拉伸变形与改色\n- Slogan：{b['slogan']}\n")


def md_assets(sc, rows=None):
    rows = rows if rows is not None else sc["assets"]
    L = [f"# {sc['brand']['product']} · 资产清单", "", "| 资产 | 类型 | 规格 | 来源 | 授权 |", "|---|---|---|---|---|"]
    L += [f"| {a['name']} | {a['type']} | {a['spec']} | {a['source']} | {a['license']} |" for a in rows]
    return "\n".join(L) + "\n"


def srt(sc):
    t, out, n = 0.0, [], 1
    fmt = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(round(x % 1 * 1000)):03d}"
    for s in sc["storyboard"]:
        text = s["vo"] or s["sub"]
        if text:
            out += [str(n), f"{fmt(t)} --> {fmt(t + s['dur'])}", text, ""]
            n += 1
        t += s["dur"]
    return "\n".join(out)


# ---------------- 图像渲染 ----------------

def font(path, size):
    return ImageFont.truetype(path, int(size))


def wrap(draw, text, fnt, width):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=fnt) > width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + ([cur] if cur else [])


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c, d, k):
    return tuple(int(a * (1 - k) + b * k) for a, b in zip(c, d))


def render_shot(sc, idx, shot, size, ai_label=True, typo=False, logo_card=False):
    W, H = size
    u = min(W, H) / 1080
    brand = sc["brand"]
    col = hex_rgb(brand["color"])
    if logo_card:
        im = Image.new("RGB", size, (250, 250, 250))
        d = ImageDraw.Draw(im)
        f = font(FONT_B, 150 * u)
        d.text((W / 2, H / 2 - 60 * u), brand["name"], font=f, fill=col, anchor="mm")
        d.text((W / 2, H / 2 + 90 * u), brand["slogan"], font=font(FONT_R, 50 * u), fill=(90, 90, 90), anchor="mm")
        return im
    bg = mix(col, (15, 15, 20), 0.65 + 0.05 * (idx % 3))
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    # 画面区
    m = 60 * u
    top, bottom = H * 0.12, H * 0.70
    d.rounded_rectangle([m, top, W - m, bottom], radius=30 * u, fill=mix(col, (40, 40, 48), 0.45))
    meta = f"镜 {idx + 1} · {shot['size']} · {shot['angle']} · {shot['move']}"
    d.text((W / 2, top + 50 * u), meta, font=font(FONT_R, 34 * u), fill=(220, 220, 220), anchor="mm")
    fv = font(FONT_R, 50 * u)
    y = top + 120 * u
    for line in wrap(d, shot["visual"], fv, W - 2 * m - 80 * u)[:10]:
        d.text((m + 40 * u, y), line, font=fv, fill=(255, 255, 255))
        y += 70 * u
    # 品牌角标
    fb = font(FONT_B, 42 * u)
    tw = d.textlength(brand["name"], font=fb)
    d.rounded_rectangle([W - m - tw - 40 * u, 30 * u, W - m, 100 * u], radius=12 * u, fill=(255, 255, 255))
    d.text((W - m - tw - 20 * u, 65 * u), brand["name"], font=fb, fill=col, anchor="lm")
    if ai_label:
        d.rounded_rectangle([m, 30 * u, m + 190 * u, 100 * u], radius=12 * u, fill=(0, 0, 0))
        d.text((m + 95 * u, 65 * u), "AI生成", font=font(FONT_B, 40 * u), fill=(255, 255, 255), anchor="mm")
    sub = shot["sub"]
    if typo:
        for a, b in TYPOS.items():
            sub = sub.replace(a, b)
    if sub:
        fs = font(FONT_B, 62 * u)
        sy = H * 0.76
        for line in wrap(d, sub, fs, W - 2 * m):
            d.text((W / 2, sy), line, font=fs, fill=(255, 255, 255), anchor="mm", stroke_width=int(5 * u), stroke_fill=(0, 0, 0))
            sy += 85 * u
    if sc.get("global_note"):
        d.text((W / 2, H - 40 * u), sc["global_note"].split("：")[-1], font=font(FONT_R, 30 * u), fill=(230, 230, 230), anchor="mm")
    return im


def render_kv(sc, size=(1080, 1920), name=None):
    W, H = size
    col = hex_rgb(sc["brand"]["color"])
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=mix((245, 247, 250), col, 0.15 + 0.5 * y / H))
    # 产品包装示意
    cx, cy = W / 2, H * 0.48
    d.rounded_rectangle([cx - 230, cy - 420, cx + 230, cy + 420], radius=60, fill=col, outline=(255, 255, 255), width=8)
    d.rectangle([cx - 230, cy - 120, cx + 230, cy + 120], fill=(255, 255, 255))
    d.text((cx, cy - 30), name or sc["brand"]["name"], font=font(FONT_B, 110), fill=col, anchor="mm")
    sub = sc["brand"]["product"].replace(sc["brand"]["name"], "").strip()
    fs = 40
    while fs > 16 and d.textlength(sub, font=font(FONT_R, fs)) > 420:
        fs -= 2
    d.text((cx, cy + 70), sub, font=font(FONT_R, fs), fill=(60, 60, 60), anchor="mm")
    d.text((W / 2, H * 0.12), name or sc["brand"]["name"], font=font(FONT_B, 120), fill=(255, 255, 255), anchor="mm", stroke_width=4, stroke_fill=col)
    d.text((W / 2, H * 0.88), sc["brand"]["slogan"], font=font(FONT_R, 64), fill=(40, 40, 40), anchor="mm")
    return im


def render_character(sc, view, hair=(30, 30, 30), shirt=(245, 245, 245), hair_long=False, size=(1080, 1920)):
    W, H = size
    im = Image.new("RGB", size, (236, 238, 242))
    d = ImageDraw.Draw(im)
    cx = W / 2 if view == "正面" else W / 2 + 40
    d.ellipse([cx - 150, 380, cx + 150, 720], fill=(240, 205, 180))  # 脸
    if hair_long:
        d.rectangle([cx - 175, 420, cx + 175, 1000], fill=hair)
        d.ellipse([cx - 150, 380, cx + 150, 720], fill=(240, 205, 180))
    d.chord([cx - 170, 330, cx + 170, 640], 180, 360, fill=hair)  # 头发
    if view == "正面":
        d.ellipse([cx - 70, 520, cx - 40, 550], fill=(40, 40, 40))
        d.ellipse([cx + 40, 520, cx + 70, 550], fill=(40, 40, 40))
    else:
        d.ellipse([cx + 70, 520, cx + 100, 550], fill=(40, 40, 40))
    d.rounded_rectangle([cx - 260, 760, cx + 260, 1500], radius=80, fill=shirt, outline=(120, 120, 120), width=4)
    d.rectangle([cx - 200, 1500, cx + 200, 1800], fill=(60, 64, 80))
    d.text((W / 2, 150), f"角色设定 · {view}", font=font(FONT_B, 70), fill=(30, 30, 30), anchor="mm")
    lead = next((a["name"].split("-")[-1].split("（")[0] for a in sc["assets"] if a["name"].startswith("角色设定图")), "主角")
    d.text((W / 2, 250), lead, font=font(FONT_R, 50), fill=(80, 80, 80), anchor="mm")
    return im


def render_endcard(sc, color=None, stretch=1.0, size=(1080, 1920)):
    W, H = size
    col = hex_rgb(color or sc["brand"]["color"])
    im = Image.new("RGB", size, (250, 250, 250))
    logo = Image.new("RGBA", (900, 260), (0, 0, 0, 0))
    ImageDraw.Draw(logo).text((450, 130), sc["brand"]["name"], font=font(FONT_B, 180), fill=col, anchor="mm")
    if stretch != 1.0:
        logo = logo.resize((int(900 * stretch), int(260 / stretch)))
    im.paste(logo, (int(W / 2 - logo.width / 2), int(H * 0.35 - logo.height / 2)), logo)
    d = ImageDraw.Draw(im)
    d.text((W / 2, H * 0.48), sc["brand"]["slogan"], font=font(FONT_R, 60), fill=(70, 70, 70), anchor="mm")
    cta = sc["storyboard"][-1]["sub"] or "了解更多"
    fb = font(FONT_B, 48)
    tw = d.textlength(cta, font=fb)
    d.rounded_rectangle([W / 2 - tw / 2 - 50, H * 0.62 - 60, W / 2 + tw / 2 + 50, H * 0.62 + 60], radius=60, fill=col)
    d.text((W / 2, H * 0.62), cta, font=fb, fill=(255, 255, 255), anchor="mm")
    return im


# ---------------- 视频渲染 ----------------

def render_video(sc, path, segments, size, audio="normal"):
    """segments: [{"img": Image|None(黑场), "dur": 秒, "noise": bool}]"""
    W, H = size
    tmp = path.parent / "_frames"
    tmp.mkdir(exist_ok=True)
    args, filters, total = [], [], 0.0
    for i, seg in enumerate(segments):
        if seg["img"] is None:
            args += ["-f", "lavfi", "-t", f"{seg['dur']}", "-i", f"color=black:s={W}x{H}:r={FPS}"]
        else:
            p = tmp / f"seg{i}.png"
            seg["img"].save(p)
            args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg['dur']}", "-i", str(p)]
        chain = f"[{i}:v]scale={W}:{H},setsar=1,format=yuv420p"
        if seg.get("noise", True) and seg["img"] is not None:
            chain += ",noise=alls=10:allf=t"
        filters.append(chain + f"[v{i}]")
        total += seg["dur"]
    n = len(segments)
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]")
    maps = ["-map", "[v]"]
    if audio != "none":
        args += ["-f", "lavfi", "-t", f"{total}", "-i", "sine=f=220:sample_rate=48000",
                 "-f", "lavfi", "-t", f"{total}", "-i", "sine=f=330:sample_rate=48000:beep_factor=4",
                 "-f", "lavfi", "-t", f"{total}", "-i", "anoisesrc=color=pink:amplitude=0.05:sample_rate=48000"]
        target = {"normal": -15, "quiet": -36, "clip": -15}[audio]
        post = ",volume=24dB" if audio == "clip" else ""
        # 音量随时间起伏，模拟真实配乐的动态（避免响度范围为 0）
        filters.append(f"[{n}:a][{n + 1}:a][{n + 2}:a]amix=inputs=3,volume='0.35+0.65*abs(sin(PI*t/4))':eval=frame,"
                       f"loudnorm=I={target}:TP=-1.5:LRA=11{post},aresample=48000[a]")
        maps += ["-map", "[a]", "-c:a", "aac", "-b:a", "128k"]
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args, "-filter_complex", ";".join(filters), *maps,
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-r", str(FPS), "-t", f"{total}", str(path)]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp)


def video_segments(sc, size, ai_label=True, typo=False, logo_open=False, no_cta=False, black=False, freeze=False):
    shots = sc["storyboard"][:-1] if no_cta else sc["storyboard"]
    segs = []
    for i, s in enumerate(shots):
        if logo_open and i == 0:
            segs.append({"img": render_shot(sc, i, s, size, logo_card=True), "dur": max(s["dur"], 3), "noise": True})
            continue
        segs.append({"img": render_shot(sc, i, s, size, ai_label, typo), "dur": s["dur"], "noise": not (freeze and i == 2)})
        if freeze and i == 2:
            segs[-1]["dur"] = s["dur"] + 2
        if black and i == 1:
            segs.append({"img": None, "dur": 1.5})
    return segs


# ---------------- 变体定义 ----------------
# expect.redlines：必须命中的红线；expect.target：应明显降分的维度（第一个为主目标）
# kind：base / redline / quality / invariance

def mid(sc):
    return len(sc["storyboard"]) // 2


def op(fn):
    def wrapper(sc):
        sc = copy.deepcopy(sc)
        fn(sc)
        return sc
    return wrapper


V = lambda sc: sc["violations"]

CREATIVE_OPS = {
    "cr_extreme": ("redline", ["R2"], [], "提案加入极限用语", op(lambda s: s["proposal"].update({"广告主张": V(s)["extreme"]}))),
    "cr_efficacy": ("redline", ["R2"], [], "提案加入功效断言", op(lambda s: s["proposal"].update({"广告主张": V(s)["efficacy"]}))),
    "cr_ip": ("redline", ["R3"], [], "故事线使用未授权 IP", op(lambda s: s["proposal"].update({"故事线": V(s)["ip"] + "；" + s["proposal"]["故事线"]}))),
    "cr_offbrief": ("quality", [], ["C1"], "提案目标人群偏离 brief", op(lambda s: s["proposal"].update({"用户洞察": V(s)["offbrief"], "故事线": V(s)["offbrief"] + "；" + s["proposal"]["故事线"]}))),
    "cr_generic_insight": ("quality", [], ["C2"], "洞察空泛", op(lambda s: s["proposal"].update({"用户洞察": GENERIC_INSIGHT}))),
    "cr_cliche": ("quality", [], ["C3"], "创意套路化", op(lambda s: s["proposal"].update({"创意概念": "产品展示＋口播介绍卖点＋字幕轮播，结尾 Logo", "故事线": "主持人手持产品面对镜头介绍卖点，画面依次展示产品外观、功能和使用场景，结尾出现 Logo 和购买信息"}))),
    "cr_logo_hook": ("quality", [], ["C4"], "Logo 慢开场", op(lambda s: s["proposal"].update({"开场钩子": "开场 5 秒播放企业 Logo 动画与品牌发展历程介绍，随后进入正片"}))),
    "cr_brand_late": ("quality", [], ["C5"], "品牌只在片尾出现", op(lambda s: s["proposal"].update({"品牌露出": "为保证故事沉浸感，全片不出现产品和品牌，仅在最后 1 秒出现 Logo"}))),
    "cr_overload": ("quality", [], ["C6"], "卖点堆砌", op(lambda s: s["proposal"].update({"传达信息": s["brief"]["核心信息"] + "；同时介绍品牌历史、生产工艺、原料产地、包装设计、代言人、门店分布、会员积分规则"}))),
    "cr_no_cta": ("quality", [], ["C7"], "无行动指引", op(lambda s: s["proposal"].pop("行动指引"))),
    "cr_infeasible": ("quality", [], ["C8"], "执行不可行", op(lambda s: s["proposal"].update({"执行方式": V(s)["infeasible"]}))),
}

STORYBOARD_OPS = {
    "sb_extreme": ("redline", ["R4"], [], "旁白含极限用语", op(lambda s: s["storyboard"][mid(s)].update({"vo": V(s)["extreme"], "sub": V(s)["extreme"]}))),
    "sb_efficacy": ("redline", ["R4"], [], "旁白含功效断言", op(lambda s: s["storyboard"][-2].update({"vo": V(s)["efficacy"], "sub": V(s)["efficacy"]}))),
    "sb_danger": ("redline", ["R1"], [], "危险行为示范画面", op(lambda s: s["storyboard"][1].update({"visual": V(s)["danger"]}))),
    "sb_ip": ("redline", ["R3"], [], "使用未授权作品", op(lambda s: s["storyboard"][2].update({"visual": V(s)["ip"] + "；" + s["storyboard"][2]["visual"]}))),
    "sb_contradict": ("redline", ["R2"], ["S5"], "核心信息与创意相悖", op(lambda s: (s.update({"core_override": V(s)["contradict"]}), s["storyboard"][-2].update({"vo": V(s)["contradict"], "sub": V(s)["contradict"]})))),
    "sb_logo_open": ("quality", [], ["S1"], "Logo 开场替换钩子", op(lambda s: s["storyboard"].__setitem__(0, {**s["storyboard"][0], "size": "全景", "angle": "正面", "move": "固定", "visual": "白底，品牌 Logo 缓缓浮现", "vo": "", "sub": "", "sfx": "轻音乐", "trans": "淡出", "prompt": "logo animation"}))),
    "sb_drop_fields": ("quality", [], ["S7"], "关键字段缺失", op(lambda s: [x.update({"angle": "", "move": "", "trans": "", "prompt": ""}) for x in s["storyboard"]])),
    "sb_continuity": ("quality", [], ["S3"], "服装道具不连贯、越轴", op(lambda s: (s["storyboard"][0].update({"visual": s["storyboard"][0]["visual"] + "（主角穿红色连帽卫衣，戴棒球帽）", "trans": "跳切"}), s["storyboard"][1].update({"visual": s["storyboard"][1]["visual"] + "（同一时刻，主角改穿蓝色西装、未戴帽子；机位越过轴线到人物另一侧）"})))),
    "sb_no_sound": ("quality", [], ["S4"], "无声音设计", op(lambda s: [x.update({"vo": "", "sub": "", "sfx": ""}) for x in s["storyboard"]])),
    "sb_wrong_platform": ("quality", [], ["S6"], "画幅与时长不符平台", op(lambda s: (s.update({"aspect_override": "16:9" if s["platform"]["aspect"] == "9:16" else "9:16"}), [x.update({"dur": x["dur"] * 4}) for x in s["storyboard"]]))),
    "sb_hard_gen": ("quality", [], ["S7"], "高难度不可生成画面", op(lambda s: [x.update({"visual": x["visual"] + "；画面中五人围坐互相击掌、传递手机，镜头快速 360° 环绕，背景大屏滚动显示整段中文文案"}) for x in s["storyboard"]])),
    "sb_monotone": ("quality", [], ["S2"], "镜头语言单一", op(lambda s: [x.update({"size": "中景", "angle": "平视", "move": "固定"}) for x in s["storyboard"]])),
    "sb_no_cta": ("quality", [], ["S1", "S5"], "删除 CTA 镜头", op(lambda s: s["storyboard"].pop())),
}

ASSET_OPS = {
    "as_low_res": ("quality", [], ["A1"], "主视觉分辨率不足", None),
    "as_blur": ("quality", [], ["A2"], "主视觉模糊、压缩严重", None),
    "as_inconsistent": ("quality", [], ["A3"], "角色侧面与正面不一致", None),
    "as_brand_off": ("quality", [], ["A4"], "落版 Logo 改色且拉伸变形", None),
    "as_wrong_name": ("redline", ["R2"], [], "主视觉产品名错误", None),
    "as_font": ("redline", ["R1"], [], "字体未获商用授权", None),
    "as_music": ("redline", ["R1"], [], "音乐未授权", None),
    "as_portrait": ("redline", ["R1"], [], "路人肖像未授权", None),
}

VIDEO_OPS = {
    "v_extreme": ("redline", ["R1"], [], "字幕含极限用语"),
    "v_no_ai_label": ("redline", ["R2"], [], "AI 生成内容缺少显式标识"),
    "v_black": ("redline", ["R5"], [], "中段插入 1.5 秒黑场"),
    "v_freeze": ("redline", ["R5"], [], "中段画面冻结"),
    "v_quiet": ("quality", [], ["V4"], "响度过低（约 -36 LUFS）"),
    "v_clip": ("quality", [], ["V4"], "音频削波失真"),
    "v_no_audio": ("quality", [], ["V4"], "无音轨"),
    "v_aspect": ("quality", [], ["V8"], "画幅与平台不符"),
    "v_low_res": ("quality", [], ["V3", "V8"], "分辨率 360x640"),
    "v_logo_open": ("quality", [], ["V1"], "Logo 开场替换钩子"),
    "v_no_cta": ("quality", [], ["V7"], "删除 CTA 落版"),
    "v_typo": ("quality", [], ["V8"], "字幕错别字"),
}

LOFI_NOTE = {
    "asset": ("# 评审说明\n\n本批资产为**低保真示意稿**（扁平占位图），用于在正式制作前确认构图、角色设定、品牌元素与授权。"
              "请不要因为「是示意稿、不是写实/成品画质」本身扣分，也不要因为清单中列出但未随附的资产扣分；"
              "其余问题（尺寸规格、清晰度与压缩瑕疵、角色前后一致性、品牌名与 Logo 是否符合规范、授权）照常严格评审。\n"),
    "video": ("# 评审说明\n\n本片为**动态分镜预演（animatic）**：每个镜头用一张卡片表示，卡片中的文字描述即该镜头的实际画面内容，"
              "请把画面描述当作已拍摄的画面来评审，不要因为「是预演、没有真实影像」本身扣分。"
              "预演卡片叠加了动态颗粒，正常卡片不会被程序判为冻结；因此程序报告的黑帧区间与冻结帧起点均为真实的技术问题，应按硬伤处理。"
              "技术参数（分辨率、画幅、响度）、字幕、AI 标识、品牌与 CTA 照常严格评审。\n"),
}

INVARIANCE = {"inv_fluff": "追加无信息量的套话", "inv_prose": "表格改为段落叙述", "inv_shuffle": "资产顺序打乱"}


# ---------------- 构建 ----------------

def check_base(sc):
    total = sum(s["dur"] for s in sc["storyboard"])
    assert abs(total - sc["platform"]["duration"]) < 1e-6, f"{sc['id']} 分镜总时长 {total} ≠ {sc['platform']['duration']}"
    text = json.dumps({k: sc[k] for k in ("brief", "proposal", "storyboard", "assets")}, ensure_ascii=False)
    bad = [w for w in FORBIDDEN if w in text]
    assert not bad, f"{sc['id']} 基准样本含禁用词：{bad}"
    subs = "".join(s["sub"] for s in sc["storyboard"])
    assert sum(subs.count(k) for k in TYPOS) >= 2, f"{sc['id']} 字幕可注入错别字不足"


def platform_hint(sc, size=None):
    pf = sc["platform"]
    w, h = pf["size"]
    return f"{pf['name']}，要求 {pf['aspect']} {w}x{h}，时长 {pf['duration']} 秒，响度参考 {pf['loudness']}，真峰值 ≤ -1 dBTP"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path.relative_to(HERE))


def label(case_id, sc, stage, variant, kind, redlines, target, desc, inputs):
    base = f"{sc['id']}_{stage}_base"
    return {"case_id": case_id, "scenario": sc["id"], "split": "dev" if sc["id"] in DEV_SCENARIOS else "test",
            "industry": sc["industry"], "stage": stage, "variant": variant,
            "kind": kind, "description": desc, "base_case_id": None if variant == "base" else base,
            "expect": {"redlines": redlines, "target": target,
                       "no_redline": kind in ("base", "quality", "invariance"),
                       "verdict_not": ["通过"] if kind in ("redline",) else []},
            "label_source": {"base": "红线=构造（基准经禁用词校验）；质量=专家先验",
                             "invariance": "构造（内容不变）"}.get(kind, "构造（定向注入）"),
            "inputs": inputs}


def build_creative(sc):
    out = []
    d = OUT / "cases"
    cid = f"{sc['id']}_creative_base"
    out.append(label(cid, sc, "creative", "base", "base", [], [], "基准创意", {"files": [write(d / cid / "creative.md", md_creative(sc))]}))
    for v, (kind, rl, tg, desc, fn) in CREATIVE_OPS.items():
        cid = f"{sc['id']}_creative_{v}"
        out.append(label(cid, sc, "creative", v, kind, rl, tg, desc, {"files": [write(d / cid / "creative.md", md_creative(fn(sc)))]}))
    for v, kw in (("inv_fluff", {"fluff": True}), ("inv_prose", {"prose": True})):
        cid = f"{sc['id']}_creative_{v}"
        out.append(label(cid, sc, "creative", v, "invariance", [], [], INVARIANCE[v], {"files": [write(d / cid / "creative.md", md_creative(sc, **kw))]}))
    return out


def build_storyboard(sc):
    out = []
    d = OUT / "cases"
    ctx = write(d / f"{sc['id']}_context" / "creative.md", md_creative(sc))
    mk = lambda cid, text: {"files": [write(d / cid / "storyboard.md", text)], "context": [ctx]}
    cid = f"{sc['id']}_storyboard_base"
    out.append(label(cid, sc, "storyboard", "base", "base", [], [], "基准分镜", mk(cid, md_storyboard(sc))))
    for v, (kind, rl, tg, desc, fn) in STORYBOARD_OPS.items():
        cid = f"{sc['id']}_storyboard_{v}"
        out.append(label(cid, sc, "storyboard", v, kind, rl, tg, desc, mk(cid, md_storyboard(fn(sc)))))
    for v, kw in (("inv_fluff", {"fluff": True}), ("inv_prose", {"prose": True})):
        cid = f"{sc['id']}_storyboard_{v}"
        out.append(label(cid, sc, "storyboard", v, "invariance", [], [], INVARIANCE[v], mk(cid, md_storyboard(sc, **kw))))
    return out


def build_asset(sc):
    out = []
    d = OUT / "cases"
    size = tuple(sc["platform"]["size"])
    ctx = [write(d / f"{sc['id']}_context" / "asset_note.md", LOFI_NOTE["asset"]),
           write(d / f"{sc['id']}_context" / "storyboard.md", md_storyboard(sc)),
           write(d / f"{sc['id']}_context" / "brand_guide.md", md_brand(sc))]
    ch = sc["character"]  # 与分镜描述一致的发色/发长/服装
    pal = [(hex_rgb(ch["hair"]), hex_rgb(ch["shirt"]), ch["hair_long"]),
           ((200, 120, 40), mix(hex_rgb(ch["shirt"]), (40, 90, 200), 0.8), not ch["hair_long"])]  # 正常 / 不一致

    def make(cid, kv=None, side=None, endcard=None, rows=None, shuffle=False):
        cdir = d / cid
        cdir.mkdir(parents=True, exist_ok=True)
        imgs = {"产品主视觉KV.png": kv or render_kv(sc),
                "角色设定_正面.png": render_character(sc, "正面", *pal[0]),
                "角色设定_侧面.png": side or render_character(sc, "侧面", *pal[0]),
                "片尾落版.png": endcard or render_endcard(sc)}
        files = []
        for name, im in imgs.items():
            im.save(cdir / name)
            files.append(str((cdir / name).relative_to(HERE)))
        rows = rows if rows is not None else list(sc["assets"])
        if shuffle:
            random.Random(sc["id"]).shuffle(rows)
            random.Random(sc["id"]).shuffle(files)
        files.append(write(cdir / "资产清单.md", md_assets(sc, rows)))
        return {"files": files, "context": ctx}

    def replace_row(prefix, **kw):
        return [{**a, **kw} if a["name"].startswith(prefix) else a for a in sc["assets"]]

    variants = {
        "base": make(f"{sc['id']}_asset_base"),
        "as_low_res": make(f"{sc['id']}_asset_as_low_res", kv=render_kv(sc).resize((270, 480))),
        "as_blur": make(f"{sc['id']}_asset_as_blur", kv=jpeg_crush(render_kv(sc).filter(ImageFilter.GaussianBlur(14)))),
        "as_inconsistent": make(f"{sc['id']}_asset_as_inconsistent", side=render_character(sc, "侧面", *pal[1])),
        "as_brand_off": make(f"{sc['id']}_asset_as_brand_off", endcard=render_endcard(sc, sc["brand"]["alt_color"], stretch=1.6)),
        "as_wrong_name": make(f"{sc['id']}_asset_as_wrong_name", kv=render_kv(sc, name=sc["brand"]["typo_name"])),
        "as_font": make(f"{sc['id']}_asset_as_font", rows=replace_row("字体", name="字体：方正兰亭黑", source="从免费字体网站下载", license="未购买商用授权，暂未确认")),
        "as_music": make(f"{sc['id']}_asset_as_music", rows=replace_row("背景音乐", name="背景音乐：热门流行歌曲原曲", source="从音乐 App 下载", license="未取得授权")),
        "as_portrait": make(f"{sc['id']}_asset_as_portrait", rows=sc["assets"] + [{"name": "街拍路人照片（作背景人物）", "type": "图片", "spec": "4000x3000 JPG", "source": "摄影师街拍", "license": "未签肖像授权"}]),
        "inv_shuffle": make(f"{sc['id']}_asset_inv_shuffle", shuffle=True),
    }
    for v, inputs in variants.items():
        if v == "base":
            out.append(label(f"{sc['id']}_asset_base", sc, "asset", "base", "base", [], [], "基准资产", inputs))
        elif v.startswith("inv"):
            out.append(label(f"{sc['id']}_asset_{v}", sc, "asset", v, "invariance", [], [], INVARIANCE[v], inputs))
        else:
            kind, rl, tg, desc, _ = ASSET_OPS[v]
            out.append(label(f"{sc['id']}_asset_{v}", sc, "asset", v, kind, rl, tg, desc, inputs))
    return out


def jpeg_crush(im):
    import io
    buf = io.BytesIO()
    im.resize((im.width // 4, im.height // 4)).save(buf, "JPEG", quality=8)
    return Image.open(io.BytesIO(buf.getvalue())).resize(im.size)


def build_video(sc):
    out = []
    d = OUT / "cases"
    size = tuple(sc["platform"]["size"])
    swapped = (size[1], size[0])
    ctx = [write(d / f"{sc['id']}_context" / "video_note.md", LOFI_NOTE["video"]),
           write(d / f"{sc['id']}_context" / "storyboard.md", md_storyboard(sc))]
    ai = sc["ai_generated"]
    plan = {
        "base": ({}, "normal", size, sc),
        "v_extreme": ({}, "normal", size, STORYBOARD_OPS["sb_extreme"][4](sc)),
        "v_black": ({"black": True}, "normal", size, sc),
        "v_freeze": ({"freeze": True}, "normal", size, sc),
        "v_quiet": ({}, "quiet", size, sc),
        "v_clip": ({}, "clip", size, sc),
        "v_no_audio": ({}, "none", size, sc),
        "v_aspect": ({}, "normal", swapped, sc),
        "v_low_res": ({}, "normal", (size[0] // 3, size[1] // 3), sc),
        "v_logo_open": ({"logo_open": True}, "normal", size, sc),
        "v_no_cta": ({"no_cta": True}, "normal", size, sc),
        "v_typo": ({"typo": True}, "normal", size, sc),
    }
    if ai:
        plan["v_no_ai_label"] = ({"ai_label": False}, "normal", size, sc)
    for v, (kw, audio, sz, s2) in plan.items():
        cid = f"{sc['id']}_video_{v}"
        cdir = d / cid
        cdir.mkdir(parents=True, exist_ok=True)
        mp4 = cdir / "final.mp4"
        if not mp4.exists():
            kw = {"ai_label": ai, **kw}
            render_size = sz if v != "v_low_res" else size
            render_video(s2, mp4, video_segments(s2, render_size, **kw), sz, audio)
        sub_sc = s2 if not kw.get("no_cta") else {**s2, "storyboard": s2["storyboard"][:-1]}
        inputs = {"files": [str(mp4.relative_to(HERE))], "context": ctx,
                  "transcript": write(cdir / "subtitles.srt", srt(sub_sc)), "platform_hint": platform_hint(sc)}
        if v == "base":
            out.append(label(cid, sc, "video", "base", "base", [], [], "基准成片（分镜动态预演）", inputs))
        else:
            kind, rl, tg, desc = VIDEO_OPS[v]
            out.append(label(cid, sc, "video", v, kind, rl, tg, desc, inputs))
        print(f"  {cid}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", nargs="*", default=["creative", "storyboard", "asset", "video"])
    ap.add_argument("--scenarios", nargs="*")
    args = ap.parse_args()
    scs = json.loads((HERE / "scenarios.json").read_text())
    if args.scenarios:
        scs = [s for s in scs if s["id"] in args.scenarios]
    builders = {"creative": build_creative, "storyboard": build_storyboard, "asset": build_asset, "video": build_video}
    labels_path = OUT / "labels.jsonl"
    existing = {}
    if labels_path.exists():
        for line in labels_path.read_text().splitlines():
            r = json.loads(line)
            existing[r["case_id"]] = r
    for sc in scs:
        check_base(sc)
        for st in args.stages:
            print(f"[{sc['id']}] {st}", file=sys.stderr)
            for r in builders[st](sc):
                existing[r["case_id"]] = r
    OUT.mkdir(exist_ok=True)
    labels_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in sorted(existing.values(), key=lambda r: r["case_id"])) + "\n")
    from collections import Counter
    c = Counter((r["stage"], r["kind"]) for r in existing.values())
    print(f"共 {len(existing)} 条：" + "，".join(f"{s}/{k}={n}" for (s, k), n in sorted(c.items())))


if __name__ == "__main__":
    main()
