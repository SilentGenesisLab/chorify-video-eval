"""第二轮用例的公共部分：Builder（写材料与标签）、checks 构造函数、场景工具。各子集的生成器在 fam_*.py，入口是 cases_v2.py。

每个用例的标签里有 checks：由 score_v2.py 逐条判定的期望，标签由构造方式决定（见 DESIGN_v4.md 第 1 节 P2）。
vs 指向比较对象（主集用例、第一轮已有结果的用例或本轮用例），report=True 的只报告、不进门槛。
"""
import copy
import json
import shutil

from PIL import Image, ImageDraw

from common import ROOT, V2, data_root, load_main

import build_dataset as bd  # noqa: E402
import exemplars as ex  # noqa: E402
import inject as ij  # noqa: E402

TEST = ["S03", "S04", "S05", "S06", "S07", "S08"]
SCS = {s["id"]: s for s in json.loads((ROOT / "benchmark" / "scenarios.json").read_text(encoding="utf-8"))}
NEXT = {s: TEST[(i + 1) % len(TEST)] for i, s in enumerate(TEST)}
# 主集测试场景每关的第一轮结果都在 results/b1/r1；第二轮用例的比较对象优先复用它们，不重复花钱


REAL_FAMILIES = ("b10", "b15")  # 真实素材子集：材料和标签都在仓库外 REAL


class Builder:
    def __init__(self, full=False):
        # series：梯度 / 规模序列；tiers：e6 三档的应有结论（case_id → pass / revise / reject）
        # full=False 是精简集（STATUS_v2 §1）：子集内部被删掉的组不生成
        self.labels, self.series, self.tiers = [], {}, {}
        self.full = full
        self.main = {l["case_id"]: l for l in load_main()}
        self.data = data_root()

    def add(self, cid, family, group, stage, sc, inputs, checks, desc, **extra):
        """expect 留空：第一轮 score.py 的 b1–b8 只看主集和 probes，不会误算第二轮用例。"""
        assert all(c["key"].startswith(family + ".") for c in checks), f"{cid}：check 的 key 必须以 {family}. 开头"
        assert cid not in {l["case_id"] for l in self.labels}, f"重复 case_id：{cid}"
        self.labels.append({
            "case_id": cid, "family": family, "group": group, "scenario": sc["id"] if sc else None, "split": "test",
            "industry": sc["industry"] if sc else None, "stage": stage, "variant": group, "kind": family, "probe": family,
            "description": desc, "base_case_id": extra.pop("base", None), "checks": checks,
            "expect": {"redlines": [], "target": [], "no_redline": False, "verdict_not": []},
            "label_source": extra.pop("source", "构造（第二轮）"), "inputs": inputs, **extra})
        return cid

    # ---- 文件 ----
    @staticmethod
    def rel(cid, name):
        """真实素材用例写到仓库外（real/...），合成用例写到 v2/cases/。"""
        return f"real/cases/{cid}/{name}" if cid.startswith(REAL_FAMILIES) else f"v2/cases/{cid}/{name}"

    def path(self, cid, name):
        from common import resolve
        p = resolve(self.rel(cid, name))
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def text(self, cid, name, s):
        self.path(cid, name).write_text(s, encoding="utf-8")
        return self.rel(cid, name)

    def image(self, cid, name, im, **save_kw):
        p = self.path(cid, name)
        if not p.exists():
            im.save(p, **save_kw)
        return self.rel(cid, name)

    def media(self, cid, name, make):
        """make(dst) 生成媒体文件；已存在跳过（媒体生成慢，重跑只补缺）。"""
        p = self.path(cid, name)
        if not p.exists():
            tmp = p.with_name("_tmp_" + p.name)
            make(tmp)
            tmp.replace(p)
        return self.rel(cid, name)

    # ---- 主集材料 ----
    def main_inputs(self, sid, stage, variant="base"):
        """主集用例的 inputs（路径统一成 /，主集标签里是 Windows 的 \\）。"""
        inp = copy.deepcopy(self.main[f"{sid}_{stage}_{variant}"]["inputs"])
        fix = lambda p: p.replace("\\", "/")
        for k in ("files", "context"):
            if k in inp:
                inp[k] = [fix(p) for p in inp[k]]
        if inp.get("transcript"):
            inp["transcript"] = fix(inp["transcript"])
        return inp

    def main_file(self, rel):
        return self.data / rel

    def asset_images(self, sid, variant="base"):
        """主集资产用例的 4 张图：{文件名: PIL.Image}。"""
        inp = self.main_inputs(sid, "asset", variant)
        return {p.rsplit("/", 1)[-1]: Image.open(self.data / p).convert("RGB") for p in inp["files"] if p.endswith(".png")}

    def asset_case(self, cid, sid, images, rows=None, list_md=None, context=None):
        """资产用例：images = [(文件名, PIL.Image | 主集相对路径)]，清单默认取场景资产表。"""
        sc = SCS[sid]
        files = []
        for name, im in images:
            if isinstance(im, str):
                dst = self.path(cid, name)
                if not dst.exists():
                    shutil.copy(self.data / im, dst)
                files.append(self.rel(cid, name))
            else:
                files.append(self.image(cid, name, im))
        files.append(self.text(cid, "资产清单.md", list_md or bd.md_assets(sc, rows)))
        ctx = self.main_inputs(sid, "asset")["context"] if context is None else context
        return {"files": files, "context": ctx}

    def video_base(self, sid):
        return self.data / self.main_inputs(sid, "video")["files"][0]

    def video_case(self, cid, sid, make=None, src=None, transcript="base", context="base", hint=None, name="final.mp4"):
        base = self.main_inputs(sid, "video")
        if make:
            f = self.media(cid, name, make)
        else:
            f = src or base["files"][0]
        inp = {"files": [f], "platform_hint": hint or base["platform_hint"]}
        if context == "base":
            inp["context"] = base["context"]
        elif context:
            inp["context"] = context
        if transcript == "base":
            inp["transcript"] = base["transcript"]
        elif transcript:
            inp["transcript"] = transcript
        return inp

    def creative_case(self, cid, sc, text=None):
        return {"files": [self.text(cid, "creative.md", text or bd.md_creative(sc))]}

    def storyboard_case(self, cid, sc, ctx_sc=None, ctx=None, text=None):
        """上下文默认是主集的创意；ctx_sc 给出另一份创意场景；ctx=[] 表示不给上下文。"""
        if ctx is None:
            ctx = [self.text(cid, "creative.md", bd.md_creative(ctx_sc))] if ctx_sc else \
                self.main_inputs(sc["id"], "storyboard")["context"]
        return {"files": [self.text(cid, "storyboard.md", text or bd.md_storyboard(sc))], "context": ctx}


# ---------------- 期望（checks） ----------------
# 每条 check 由 score_v2.py 判定，key 是它计入的指标；report=True 只报告不进门槛。
#   redline  ids 里每条红线：hit=True 要求过半采样命中（产品口径），hit=False 要求未命中
#   delta    x(a) − x(b) 落在 [lo, hi]：x 是 dims 的均分平均（dims="total" 用加权总分）；a 缺省为本例
#            drop(min=1) 即 delta(vs 本例 → 基准) ≥ 1；不升即 hi=0.2
#   verdict  结论属于 allow 或不属于 deny
#   mention  where（"dims:A3"、"redlines:R1"、"top_fixes"、"top1"、"issues"、"all"）里正则命中，过半采样成立
#   corr     不逐例判定：同一 key 的全部用例，dims 均分与 truth 的 Spearman 相关
#   tier     不逐例判定：同一 key 的全部用例，结论三档与 truth 档的加权 κ 与跨档错
# 同一 key 下的 rate 指标 = 成立的 check 数 / 可判定的 check 数；delta 另报均值。

def C(t, key, **kw):
    return {"t": t, "key": key, **kw}


def redline(key, ids, hit=True, clean=None, **kw):
    """clean=基准用例：基准已经命中同一条红线时不可判定（真实素材本身可能就有问题）。"""
    return C("redline", key, ids=list(ids), hit=hit, clean=clean, **kw)


def delta(key, dims, b, a=None, lo=None, hi=None, **kw):
    return C("delta", key, dims=dims if dims == "total" else list(dims), a=a, b=b, lo=lo, hi=hi, **kw)


def drop(key, dims, vs, min=1.0, **kw):
    """本例比 vs 降 ≥ min。"""
    return delta(key, dims, b=None, a=vs, lo=min, **kw)


def no_rise(key, dims, vs, max=0.2, **kw):
    """本例比 vs 升不超过 max。"""
    return delta(key, dims, b=vs, hi=max, **kw)


def better(key, dims, good, bad, margin=0.0, **kw):
    """good 比 bad 严格高（> margin）。"""
    return delta(key, dims, a=good, b=bad, lo=margin + 1e-6, **kw)


def verdict(key, allow=None, deny=None, **kw):
    return C("verdict", key, allow=allow, deny=deny, **kw)


def mention(key, where, pattern, clean=None, **kw):
    """clean=对照用例：对照里同一位置过半采样也匹配时不可判定（正则分不出是不是在说注入的问题）。"""
    return C("mention", key, where=where, pattern=pattern, clean=clean, **kw)


def locus(key, where, **loc):
    """定位：where（同 mention）里提到的位置与注入位置一致，过半采样成立。loc 取其一：
    shot=镜号、t=[起, 止]（容差 ±1 秒）、image=文件名或别名正则、quote=注入句片段。
    where 是红线时只在该红线命中的采样里看（"命中了但指错地方"才算错）。"""
    return C("locus", key, where=where, loc=loc)


def order(key, dims, ids, tol=0.25, **kw):
    """ids 依次不升（相邻允许升 tol），且首 > 尾。"""
    return C("order", key, dims=dims if dims == "total" else list(dims), ids=list(ids), tol=tol, **kw)


def corr(key, dims, truth, **kw):
    return C("corr", key, dims=list(dims), truth=truth, **kw)


def tier(key, truth, **kw):
    return C("tier", key, truth=truth, **kw)


def mut(sc, fn):
    """深拷贝后改场景：fn 原地修改（返回值忽略），或像 build_dataset 的 op() 那样返回新场景。"""
    s = copy.deepcopy(sc)
    r = fn(s)
    return r if isinstance(r, dict) else s


def main_id(sid, stage, variant="base"):
    return f"{sid}_{stage}_{variant}"


def shot_times(sc):
    """主集成片按分镜时长逐镜拼接：返回每镜 (起, 止)。"""
    t, out = 0.0, []
    for s in sc["storyboard"]:
        out.append((t, t + s["dur"]))
        t += s["dur"]
    return out


def render_kv(sc, name=None, slogan=None, name_size=110, top_name=None, extra=None, sub=None):
    """主集 render_kv 的参数化版本：包装上的品牌名（name、字号）、顶部大标题（top_name，缺省同 name）、slogan、
    包装上品牌名下面的型号 / 品类行（sub）分别可改。
    参数都取缺省时与 bd.render_kv 逐像素一致（test_inject 校验）。"""
    W, H = 1080, 1920
    brand = sc["brand"]["name"]
    col = bd.hex_rgb(sc["brand"]["color"])
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=bd.mix((245, 247, 250), col, 0.15 + 0.5 * y / H))
    cx, cy = W / 2, H * 0.48
    d.rounded_rectangle([cx - 230, cy - 420, cx + 230, cy + 420], radius=60, fill=col, outline=(255, 255, 255), width=8)
    d.rectangle([cx - 230, cy - 120, cx + 230, cy + 120], fill=(255, 255, 255))
    d.text((cx, cy - 30), name or brand, font=bd.font(bd.FONT_B, name_size), fill=col, anchor="mm")
    sub = sub or sc["brand"]["product"].replace(brand, "").strip()
    fs = 40
    while fs > 16 and d.textlength(sub, font=bd.font(bd.FONT_R, fs)) > 420:
        fs -= 2
    d.text((cx, cy + 70), sub, font=bd.font(bd.FONT_R, fs), fill=(60, 60, 60), anchor="mm")
    d.text((W / 2, H * 0.12), top_name or name or brand, font=bd.font(bd.FONT_B, 120), fill=(255, 255, 255), anchor="mm",
           stroke_width=4, stroke_fill=col)
    d.text((W / 2, H * 0.88), slogan or sc["brand"]["slogan"], font=bd.font(bd.FONT_R, 64), fill=(40, 40, 40), anchor="mm")
    return extra(im) if extra else im


def size_of(sc):
    return tuple(sc["platform"]["size"])


def render_video(sc, dst, segments=None, size=None, audio="normal", **seg_kw):
    """按主集方式渲染预演成片；segments 缺省由 video_segments 生成（AI 标识按场景）。"""
    size = size or size_of(sc)
    if segments is None:
        segments = bd.video_segments(sc, size, **{"ai_label": sc["ai_generated"], **seg_kw})
    dst.parent.mkdir(parents=True, exist_ok=True)
    bd.render_video(sc, dst, segments, size, audio)


def shot_seg(sc, i, size=None, dur=None, **kw):
    s = sc["storyboard"][i]
    size = size or size_of(sc)
    return {"img": bd.render_shot(sc, i, s, size, sc["ai_generated"], **kw), "dur": dur or s["dur"], "noise": True}


def video_with_text(b, cid, sc, make=None, srt_sc=None, context=None, transcript="auto", hint=None, **render_kw):
    """渲染成片 + 按分镜写字幕；context 缺省用主集成片的上下文（预演说明 + 主集分镜）。"""
    f = b.media(cid, "final.mp4", make or (lambda dst: render_video(sc, dst, **render_kw)))
    base = b.main_inputs(sc["id"], "video")
    inp = {"files": [f], "platform_hint": hint or base["platform_hint"],
           "context": base["context"] if context is None else context}
    if transcript == "auto":
        inp["transcript"] = b.text(cid, "subtitles.srt", bd.srt(srt_sc or sc))
    elif transcript:
        inp["transcript"] = transcript
    return inp


def video_ctx(b, cid, sc, note=True):
    """成片上下文：预演说明 + 给定场景的分镜（不同于主集时另写一份）。"""
    files = [b.main_inputs(sc["id"], "video")["context"][0]] if note else []
    return files + [b.text(cid, "storyboard_ctx.md", bd.md_storyboard(sc))]


def asset_ctx(b, cid, sc, note=True, storyboard=True, brand=True):
    """资产上下文：低保真说明 / 分镜 / 品牌规范，可分别去掉；内容与主集相同时直接引用主集文件。"""
    main_ctx = b.main_inputs(sc["id"], "asset")["context"]  # [说明, 分镜, 品牌规范]
    out = []
    if note:
        out.append(main_ctx[0])
    if storyboard is True:
        out.append(main_ctx[1])
    elif storyboard:
        out.append(b.text(cid, "storyboard_ctx.md", bd.md_storyboard(storyboard)))
    if brand is True:
        out.append(main_ctx[2])
    elif brand:
        out.append(b.text(cid, "brand_ctx.md", brand))
    return out


def main_assets(b, sid):
    """主集资产基准的 4 张图：[(文件名, 主集相对路径)]，顺序与主集一致。"""
    return [(p.rsplit("/", 1)[-1], p) for p in b.main_inputs(sid, "asset")["files"] if p.endswith(".png")]


def character_pal(sc):
    ch = sc["character"]
    return bd.hex_rgb(ch["hair"]), bd.hex_rgb(ch["shirt"]), ch["hair_long"]
