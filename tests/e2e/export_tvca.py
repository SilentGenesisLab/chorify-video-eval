"""端到端评测的用例导出：从 tvcagent 生产流水线（用户 brief → 成片）的已完成 roll 里，导出四道关卡的评审材料。

python tests/e2e/export_tvca.py --tvca <tvcagent 根目录> [--rolls R1 R2 …] [--out %TEMP%/vr_e2e]

只读 tvcagent 的 runs/spine.db，不改它。每个 roll 导出：
- creative：选中的创意方向 + 脚本大创意与节拍（参考：用户 brief 原文、客户文档）
- storyboard：终版分镜表（参考：上面的创意提案）
- asset：终版关键帧 + 资产清单（参考：分镜表、客户产品图）
- video：终版成片（带字幕版优先），字幕 .srt 作台词（参考：分镜表）

另外把 tvcagent 审核门上「人工驳回过」的关键帧 / 片段做成负例：
- 关键帧：终版关键帧里把被驳回的那几镜换回驳回时的版本
- 片段：终版成片（无字幕版）里把被驳回那镜的时间段换成驳回时的片段；配对的正例是同一条无字幕成片
负例的标签就是 tvcagent 审核人写的驳回理由。

材料可能含客户素材：默认写到仓库外的临时目录，不进 git。
"""
import argparse
import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import video_review as vr  # noqa: E402

OUT = pathlib.Path(tempfile.gettempdir()) / "vr_e2e"
DONE_KINDS = ("master", "master_sub")


class Roll:
    def __init__(self, conn, roll):
        self.c, self.id = conn, roll
        rows = conn.execute("select kind, take, payload, blob_path, created_at from artifact where roll=? order by created_at, take",
                            (roll,)).fetchall()
        self.arts = [dict(kind=k, take=t, p=json.loads(p) if p else {}, blob=b, at=a) for k, t, p, b, a in rows]
        self.brief_text = conn.execute("select brief_text from roll where id=?", (roll,)).fetchone()[0] or ""

    def all(self, kind):
        return [a for a in self.arts if a["kind"] == kind]

    def last(self, kind):
        xs = self.all(kind)
        return max(xs, key=lambda a: a["take"]) if xs else None

    def payload(self, kind):
        a = self.last(kind)
        return a["p"] if a else {}


def aspect_tag(a):
    return (a or "16:9").split()[0].replace(":", "x")


def primary_aspect(r):
    a = str(r.payload("brief").get("aspect") or "16:9")
    return "9:16" if a.startswith("9:16") else "16:9"


def shot_of(art):
    return art["p"].get("shot_id") or pathlib.Path(art["blob"] or "").name.split(".")[0].split("@")[0]


def same_aspect(art, aspect):
    a = art["p"].get("aspect")
    return a is None or a == aspect


# ---------- 文本材料 ----------

def creative_md(r):
    b, s = r.payload("brief"), r.payload("script")
    chosen = (r.payload("review:directions") or {}).get("chosen") or {}
    L = [f"# {b.get('brand') or ''} {b.get('product') or ''} · 创意提案".strip(), ""]
    L += ["## 一、Brief 要点", "",
          f"- 产品：{b.get('product', '')}", f"- 受众：{b.get('audience', '')}", f"- 投放：{b.get('platform', '')}",
          f"- 画幅 / 时长：{b.get('aspect', '')} / {b.get('duration_s', '')} 秒", f"- 调性：{b.get('tone', '')}"]
    if b.get("must_say"):
        L += ["- 必须传达：" + "；".join(map(str, b["must_say"]))]
    if b.get("must_avoid"):
        L += ["- 禁止：" + "；".join(map(str, b["must_avoid"]))]
    L += ["", "## 二、创意方向", ""]
    if chosen:
        L += [f"**{chosen.get('title', '')}**：{chosen.get('logline', '')}", "", f"- 结构：{chosen.get('structure', '')}",
              f"- 理由：{chosen.get('why', '')}", f"- 风险：{chosen.get('risk', '')}"]
    else:
        L += ["（按客户原稿执行，未另出创意方向）"]
    L += ["", f"- 大创意：{s.get('big_idea', '')}"]
    if s.get("visual_approach"):
        L += [f"- 视觉手法：{s['visual_approach']}"]
    L += ["", "## 三、脚本节拍", "", "| 节拍 | 时长 | 画面意图 | 屏幕文字 | 旁白 |", "|---|---|---|---|---|"]
    for x in s.get("beats", []):
        L.append(f"| {x.get('id')} | {x.get('duration_s')}s | {cell(x.get('intent'))} | {cell(x.get('on_screen')) or '—'} | {cell(x.get('vo')) or '—'} |")
    return "\n".join(L) + "\n"


def cell(v):
    return str(v or "").replace("|", "／").replace("\n", " ").strip()


def shots(r):
    return r.payload("shotlist").get("shots", [])


def storyboard_md(r):
    b, beats = r.payload("brief"), {x["id"]: x for x in r.payload("script").get("beats", [])}
    L = [f"# {b.get('product', '')} · 分镜脚本", "",
         f"- 投放平台：{b.get('platform', '')}　画幅：{b.get('aspect', '')}　总时长：{b.get('duration_s', '')} 秒", "",
         "| 镜号 | 时长 | 景别 | 运镜 | 画面描述 | 台词/旁白 | 字幕 | 音乐音效 | 转场 | AI 提示词/制作 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for sh in shots(r):
        # 新版分镜把画面写在 visual / phases 里，早期版本（2026-10-14/15）是平铺字段
        v = sh.get("visual") or {k: sh.get(k) for k in ("subject", "action", "camera", "transition") if sh.get(k)}
        if not sh.get("visual") and (sh.get("spec") or {}).get("lighting"):
            v["light"] = sh["spec"]["lighting"]
        ph = sh.get("phases") or []
        size = v.get("shot_size") or sh.get("framing") or ""
        cam = v.get("camera") or "；".join(p.get("camera", "") for p in ph)
        desc = "；".join(x for x in (v.get("subject"), v.get("scene"), v.get("action"), v.get("light")) if x) or \
            "；".join(f"{p.get('at_s', 0)}s 起：{p.get('subject', '')}，{p.get('action', '')}（{p.get('scene', '')}）" for p in ph)
        sub = " / ".join(cell(beats[i].get("on_screen")) for i in str(sh.get("beat", "")).split("+") if i in beats and beats[i].get("on_screen"))
        au = sh.get("audio") or {}
        music = "；".join(x for x in (au.get("bgm") and f"BGM：{au['bgm']}", au.get("sfx") and f"SFX：{au['sfx']}") if x)
        trans = v.get("transition") or (ph[-1].get("transition") if ph else "") or sh.get("transition_out") or ""
        make = "后期制作" if sh.get("source") == "post" else "AI 生成" + (f"；{(sh.get('notes') or {}).get('ai', '')}" if (sh.get("notes") or {}).get("ai") else "")
        L.append(f"| {sh['id'][1:] if sh['id'].startswith('S') else sh['id']} | {sh.get('duration_s')}s | {cell(size)} | {cell(cam)} | {cell(desc)} | "
                 f"{cell(au.get('vo')) or '—'} | {sub or '—'} | {cell(music)} | {cell(trans)} | {cell(make)} |")
    return "\n".join(L) + "\n"


# ---------- 资产 ----------

def final_keyframes(r, aspect):
    """{镜号: 最新一版关键帧}，只取主画幅。"""
    out = {}
    for a in r.all("keyframe"):
        if a["blob"] and pathlib.Path(a["blob"]).exists() and same_aspect(a, aspect):
            s = shot_of(a)
            if s not in out or a["take"] > out[s]["take"]:
                out[s] = a
    return out


def asset_list_md(r, kfs, refs):
    L = ["# 资产清单", "", "| 资产 | 类型 | 规格 | 来源 | 授权 |", "|---|---|---|---|---|"]
    for s in sorted(kfs):
        a = kfs[s]
        L.append(f"| 镜{s[1:]} 关键帧（{pathlib.Path(a['blob']).name}） | AI 生成图片 | {a['p'].get('size') or a['p'].get('aspect') or ''} | "
                 f"模型 {a['p'].get('model') or '图像生成模型'} 生成，产品外观以客户产品图为参考 | 生成工具商用条款 |")
    for p in refs:
        L.append(f"| {p.name}（产品参考） | 客户提供图片 | — | 客户提供 | 客户自有 |")
    return "\n".join(L) + "\n"


def client_assets(r, roles=("product", "logo", "ref", "auto")):
    imgs, docs = [], []
    for a in r.all("asset"):
        b = pathlib.Path(a["blob"] or "")
        if not b.exists():
            continue
        name = a["p"].get("original_name") or b.name
        if a["p"].get("media_kind") == "image" and a["p"].get("role") in roles:
            imgs.append((name, b))
        elif a["p"].get("media_kind") == "doc":
            docs.append((name, b))
    return imgs, docs


# ---------- 审核记录 → 负例 ----------

def rejected_takes(r, kind, gate, aspect):
    """[(审核记录, {镜号: 被驳回的那一版})]：同一组被驳回的版本只留一条。"""
    out, seen = [], set()
    for rv in r.all(gate):
        if rv["p"].get("decision") != "reject" or not rv["p"].get("shots"):
            continue
        took = {}
        for s in rv["p"]["shots"]:
            prior = [a for a in r.all(kind) if shot_of(a) == s and a["at"] <= rv["at"] and same_aspect(a, aspect)
                     and a["blob"] and pathlib.Path(a["blob"]).exists()]
            if prior:
                took[s] = max(prior, key=lambda a: a["at"])
        key = tuple(sorted((s, a["take"]) for s, a in took.items()))
        if took and key not in seen:
            seen.add(key)
            out.append((rv, took))
    return out


def master_files(r, aspect):
    tag = aspect_tag(aspect)
    pick = {}
    for k in DONE_KINDS:
        xs = [a for a in r.all(k) if a["blob"] and pathlib.Path(a["blob"]).exists() and (a["p"].get("aspect") in (None, aspect))
              and (tag in pathlib.Path(a["blob"]).name or a["p"].get("aspect") == aspect or "x" not in pathlib.Path(a["blob"]).name)]
        if xs:
            pick[k] = pathlib.Path(max(xs, key=lambda a: (a["at"], a["take"]))["blob"])
    return pick


def srt_for(r, aspect):
    d = r.payload("delivery").get("dir")
    cands = sorted(pathlib.Path(d).glob(f"*{aspect_tag(aspect)}*.srt")) if d and pathlib.Path(d).exists() else []
    if not cands:
        cands = sorted((pathlib.Path(d) if d else pathlib.Path(".")).glob("*.srt")) if d else []
    if cands:
        return max(cands, key=lambda p: int(p.stem.rsplit(".t", 1)[-1]) if p.stem.rsplit(".t", 1)[-1].isdigit() else 0)
    vos = [v["p"].get("text") for v in r.all("vo") if v["p"].get("text")]
    return "\n".join(vos) or None


def shot_windows(r):
    t, out = 0.0, {}
    for sh in shots(r):
        d = float(sh.get("duration_s") or 0)
        out[sh["id"]] = (t, t + d)
        t += d
    return out


def splice(master, clips, windows, dst):
    """把 clips {镜号: 片段} 盖到 master 对应时间段上（缩放到成片尺寸，保留成片音轨）。"""
    info = vr.probe_video(master)
    w, h = map(int, info["分辨率"].split("x"))
    args, chain, last = ["-i", str(master)], [], "[0:v]"
    for i, (s, clip) in enumerate(sorted(clips.items()), 1):
        t0, t1 = windows[s]
        args += ["-i", str(clip)]
        chain.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setpts=PTS-STARTPTS+{t0}/TB[c{i}]")
        chain.append(f"{last}[c{i}]overlay=0:0:eof_action=pass:enable='between(t,{t0},{t1 - 0.04})'[v{i}]")
        last = f"[v{i}]"
    cmd = [vr.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args, "-filter_complex", ";".join(chain),
           "-map", last, "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", str(dst)]
    subprocess.run(cmd, check=True)


# ---------- 导出 ----------

def write(d, name, text):
    (d / name).write_text(text, encoding="utf-8")
    return str(d / name)


def copy(d, src, name=None):
    dst = d / (name or pathlib.Path(src).name)
    if not dst.exists():
        shutil.copy2(src, dst)
    return str(dst)


def export_roll(r, out):
    aspect = primary_aspect(r)
    b = r.payload("brief")
    base = out / r.id
    base.mkdir(parents=True, exist_ok=True)
    ctx = base / "_ctx"
    ctx.mkdir(exist_ok=True)
    brief = write(ctx, "brief.md", "# 用户 brief（原文）\n\n" + r.brief_text)
    imgs, docs = client_assets(r)
    doc_ctx = [copy(ctx, p, f"客户文档_{n}") for n, p in docs if p.suffix.lower() in (".md", ".txt")]
    ref_imgs = [copy(ctx, p, f"产品参考_{n}") for n, p in imgs]
    cr = write(ctx, "creative.md", creative_md(r))
    sb = write(ctx, "storyboard.md", storyboard_md(r))
    hint = f"{b.get('platform') or '短视频平台'}，画幅 {aspect}，时长 {b.get('duration_s', '')} 秒，响度参考 -14～-16 LUFS，真峰值 ≤ -1 dBTP"
    cases = []

    def add(cid, stage, files, context, kind="final", **kw):
        cases.append({"case_id": cid, "roll": r.id, "stage": stage, "kind": kind, "files": files, "context": context,
                      "platform_hint": hint, **kw})

    human = {g: [x["p"] for x in r.all(f"review:{g}")] for g in ("brief", "directions", "script", "storyboard", "keyframes", "clips")}
    last_dec = lambda g: (human[g][-1].get("decision"), human[g][-1].get("by")) if human[g] else (None, None)

    add(f"{r.id}__creative", "creative", [cr], [brief] + doc_ctx, human=last_dec("script"))
    add(f"{r.id}__storyboard", "storyboard", [sb], [cr], human=last_dec("storyboard"))

    kfs = final_keyframes(r, aspect)
    if kfs:
        d = base / "asset_final"
        d.mkdir(exist_ok=True)
        files = [copy(d, kfs[s]["blob"], f"镜{s[1:]}_关键帧{pathlib.Path(kfs[s]['blob']).suffix}") for s in sorted(kfs)]
        files.append(write(d, "资产清单.md", asset_list_md(r, kfs, [pathlib.Path(p) for p in ref_imgs])))
        add(f"{r.id}__asset", "asset", files, [sb] + ref_imgs, human=last_dec("keyframes"))
        for i, (rv, took) in enumerate(rejected_takes(r, "keyframe", "review:keyframes", aspect), 1):
            d = base / f"asset_neg{i}"
            d.mkdir(exist_ok=True)
            mix = {**kfs, **took}
            files = [copy(d, mix[s]["blob"], f"镜{s[1:]}_关键帧{pathlib.Path(mix[s]['blob']).suffix}") for s in sorted(mix)]
            files.append(write(d, "资产清单.md", asset_list_md(r, mix, [pathlib.Path(p) for p in ref_imgs])))
            add(f"{r.id}__asset_neg{i}", "asset", files, [sb] + ref_imgs, kind="neg", pair=f"{r.id}__asset",
                shots=sorted(took), human_reject=rv["p"].get("notes", ""))

    ms = master_files(r, aspect)
    srt = srt_for(r, aspect)
    tr = None
    if srt and pathlib.Path(str(srt)).suffix == ".srt" and pathlib.Path(srt).exists():
        tr = copy(ctx, srt, "subtitles.srt")
    elif srt:
        tr = write(ctx, "transcript.txt", srt)
    final = ms.get("master_sub") or ms.get("master")
    if final:
        d = base / "video_final"
        d.mkdir(exist_ok=True)
        add(f"{r.id}__video", "video", [copy(d, final, "final.mp4")], [sb], transcript=tr, human=last_dec("clips"))
    plain = ms.get("master")
    negs = rejected_takes(r, "clip", "review:clips", aspect)
    if plain and negs:
        d = base / "video_plain"
        d.mkdir(exist_ok=True)
        pos = f"{r.id}__video_plain"
        add(pos, "video", [copy(d, plain, "final.mp4")], [sb], transcript=tr, kind="pos")
        win = shot_windows(r)
        for i, (rv, took) in enumerate(negs, 1):
            if not all(s in win for s in took):
                continue
            d = base / f"video_neg{i}"
            d.mkdir(exist_ok=True)
            dst = d / "final.mp4"
            if not dst.exists():
                splice(plain, {s: a["blob"] for s, a in took.items()}, win, dst)
            add(f"{r.id}__video_neg{i}", "video", [str(dst)], [sb], transcript=tr, kind="neg", pair=pos,
                shots=sorted(took), windows={s: win[s] for s in took}, human_reject=rv["p"].get("notes", ""))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tvca", required=True, help="tvcagent 根目录")
    ap.add_argument("--rolls", nargs="*", help="默认：所有已出成片的 roll")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    db = pathlib.Path(a.tvca) / "runs" / "spine.db"
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    rolls = a.rolls or [x for (x,) in conn.execute(
        "select distinct roll from artifact where kind in ('master','master_sub') order by roll")]
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    for rid in rolls:
        r = Roll(conn, rid)
        if not r.all("script") or not r.all("shotlist"):
            print(f"跳过 {rid}：没有脚本或分镜")
            continue
        got = export_roll(r, out)
        print(f"{rid}：{len(got)} 例（" + "、".join(f"{c['stage']}{'-' + c['kind'] if c['kind'] != 'final' else ''}" for c in got) + "）")
        cases += got
    (out / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"共 {len(cases)} 例 → {out / 'cases.json'}")


if __name__ == "__main__":
    main()
