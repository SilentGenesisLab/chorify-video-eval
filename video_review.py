#!/usr/bin/env python3
"""视频全链路评审：按 rubrics.json 对创意 / 分镜 / 资产 / 成片打分（默认 deepseek-flash，可换任意 OpenAI 兼容接口的模型）。

用法：
  python video_review.py creative  brief.md proposal.md
  python video_review.py storyboard storyboard.md frames/*.png --context brief.md
  python video_review.py asset     assets/*.png asset_list.md
  python video_review.py video     final.mp4 --context storyboard.md --transcript subs.srt

接口配置从环境变量或同目录 .env 读取：
  REVIEW_API_URL  chat/completions 地址，默认 DeepSeek 官方
  REVIEW_API_KEY  接口 Key，未设置时用 DEEPSEEK_API_KEY
  REVIEW_MODEL    默认模型，未设置时为 deepseek-flash

两种评审方式（--mode）：
  sample  同一个评审员按整套标准评 runs 次，维度取均值、红线多数票（原有方式，基准测试用这个）
  panel   分维度评审团：rubrics.json 里每个关卡的 panels 各派一个评审员，各自只看自己负责的维度，
          另有合规评审员只判红线；评审员上下文互不相通、并发执行，结论仍由程序按规则计算
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}


def env_value(name):
    """环境变量优先，其次同目录 .env。"""
    if os.environ.get(name):
        return os.environ[name]
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip() or None
    return None


def load_api_key():
    key = env_value("REVIEW_API_KEY") or env_value("DEEPSEEK_API_KEY")
    if not key:
        sys.exit("缺少 REVIEW_API_KEY / DEEPSEEK_API_KEY（环境变量或 .env）")
    return key


def api_url():
    return env_value("REVIEW_API_URL") or DEFAULT_API_URL


def default_model():
    return env_value("REVIEW_MODEL") or "deepseek-flash"


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


# ---------- 成片技术 QC（程序测量） ----------

def run_ffmpeg(args):
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", *args],
                       capture_output=True, text=True, errors="replace")
    return p.stderr


def probe_video(path):
    info = {}
    err = run_ffmpeg(["-i", str(path)])
    if m := re.search(r"Duration: (\d+):(\d+):([\d.]+)", err):
        info["时长(秒)"] = round(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), 2)
    if m := re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err):
        w, h = int(m[2]), int(m[3])
        info.update({"视频编码": m[1], "分辨率": f"{w}x{h}", "画幅": f"{w / h:.3f} ({'竖屏' if h > w else '横屏' if w > h else '方形'})"})
    if m := re.search(r"([\d.]+) fps", err):
        info["帧率"] = float(m[1])
    if m := re.search(r"Audio: (\w+).*?, (\d+) Hz, ([^,]+)", err):
        info.update({"音频编码": m[1], "采样率": int(m[2]), "声道": m[3].strip()})
    else:
        info["音频"] = "无音轨"

    if "音频" not in info:
        err = run_ffmpeg(["-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
        summary = err[err.rfind("Summary:"):]
        if m := re.search(r"I:\s+(-?[\d.]+) LUFS", summary):
            info["综合响度(LUFS)"] = float(m[1])
        if m := re.search(r"LRA:\s+([\d.]+) LU", summary):
            info["响度范围(LU)"] = float(m[1])
        if m := re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary):
            info["真峰值(dBTP)"] = m[1]

    err = run_ffmpeg(["-i", str(path), "-an", "-vf", "blackdetect=d=0.2:pix_th=0.10,freezedetect=n=0.003:d=1.0", "-f", "null", "-"])
    info["黑帧区间"] = [f"{a}s–{b}s" for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]
    info["冻结帧起点"] = [f"{t}s" for t in re.findall(r"freeze_start: ([\d.]+)", err)]
    return info


def extract_frames(path, duration, n, outdir):
    """前 3 秒每 0.5 秒一帧（看钩子），其余时长均匀抽 n 帧。"""
    times = [t / 2 for t in range(0, 6) if t / 2 < duration]
    if duration > 3:
        step = (duration - 3) / n
        times += [round(3 + step * (i + 0.5), 2) for i in range(n)]
    times.append(max(duration - 0.1, 0))  # 尾帧（CTA）
    frames = []
    for t in sorted(set(times)):
        out = Path(outdir) / f"frame_{t:07.2f}.jpg"
        subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", str(t), "-i", str(path),
                        "-frames:v", "1", "-vf", "scale='min(768,iw)':-2", "-q:v", "3", "-y", str(out)])
        if out.exists():
            frames.append((t, out))
    return frames


# ---------- Prompt ----------

def build_system_prompt(stage, rubric, panel=None):
    """panel 为空时评整套标准；否则只评 panel["dimensions"]，panel["redlines"] 为真时才判红线。"""
    s = rubric["stages"][stage]
    if panel:
        return build_panel_prompt(stage, rubric, panel)
    dims = "\n".join(
        f"- {d['id']} {d['name']}（权重 {int(d['weight'] * 100)}%）：{d['criteria']}\n"
        f"    5 分样子：{d['anchor_5']}；2 分样子：{d['anchor_2']}"
        for d in s["dimensions"])
    scale = "\n".join(f"  {k} 分 = {v}" for k, v in sorted(rubric["scale"].items(), reverse=True))
    redlines = "\n".join(f"- R{i + 1}：{r}" for i, r in enumerate(s["redlines"]))
    ids = ", ".join(d["id"] for d in s["dimensions"])
    return f"""你是资深视频内容评审专家，同时具备广告创意总监、导演、品牌经理和广告合规法务的经验。
你正在执行【{s['name']}】。评审对象：{s['input_hint']}。

## 评分刻度（所有维度通用，整数）
{scale}

## 质量维度
{dims}

## 红线（一票否决）
{redlines}

## 评审要求
1. 严格对照维度定义与锚点打分，不要因为材料篇幅长或文笔好而加分；分数要拉开，确有问题就给 2 分或 1 分，确实出色才给 5 分。
2. 每个维度必须先写 evidence：引用材料中的具体内容（镜号、时间码、原文片段、画面描述），再给分。材料中没有相关信息时，evidence 写明「材料未提供」，按缺失程度扣分。
3. issues 与 suggestions 要可执行：指出位置 + 问题 + 具体改法。
4. 红线逐条判断：仅在有明确证据时 hit=true；有疑虑但证据不足时 hit=false 并在 evidence 中说明疑点。
5. 你看不到视频动态和听不到声音时，基于给出的技术参数、关键帧和文本推断，并在 evidence 中注明「推断」。
6. 不要计算总分，总分与结论由程序计算。
7. JSON 字符串里引用原文请用「」，不要用英文双引号。

## 输出格式
只输出一个 JSON 对象，不要输出其他文字：
{{
  "dimensions": [
    {{"id": "维度ID", "evidence": "具体证据", "score": 1-5 的整数, "issues": ["问题"], "suggestions": ["改法"]}}
  ],
  "redlines": [
    {{"id": "R1", "hit": true/false, "evidence": "证据或疑点"}}
  ],
  "highlights": ["做得好的地方"],
  "top_fixes": ["按优先级排序的最重要的 3 条修改建议"],
  "summary": "100 字以内的总体评价"
}}
dimensions 必须且只能包含：{ids}；redlines 必须覆盖 R1–R{len(s['redlines'])}。"""


def build_panel_prompt(stage, rubric, panel):
    s = rubric["stages"][stage]
    mine = [d for d in s["dimensions"] if d["id"] in panel.get("dimensions", [])]
    scale = "\n".join(f"  {k} 分 = {v}" for k, v in sorted(rubric["scale"].items(), reverse=True))
    parts = [f"""你是评审团中的「{panel['name']}」评审员：{panel['role']}
你正在参与【{s['name']}】。评审对象：{s['input_hint']}。
评审团里其他评审员负责其他方面，你只对自己负责的部分下结论，不要评价职责以外的内容。"""]
    if mine:
        dims = "\n".join(
            f"- {d['id']} {d['name']}：{d['criteria']}\n    5 分样子：{d['anchor_5']}；2 分样子：{d['anchor_2']}" for d in mine)
        parts.append(f"## 评分刻度（整数）\n{scale}\n\n## 你负责的维度\n{dims}")
    if panel.get("redlines"):
        reds = "\n".join(f"- R{i + 1}：{r}" for i, r in enumerate(s["redlines"]))
        parts.append(f"## 红线（一票否决，你负责逐条判断）\n{reds}")
    parts.append("""## 评审要求
1. 先写 evidence：引用材料中的具体内容（镜号、时间码、原文片段、画面描述），再下结论；材料里没有就写「材料未提供」。
2. 分数要拉开：确有问题就给 2 分或 1 分，确实出色才给 5 分；不要因为篇幅长或文笔好而加分。
3. issues 与 suggestions 要可执行：位置 + 问题 + 具体改法。
4. 红线仅在有明确证据时 hit=true；有疑虑但证据不足时 hit=false，并在 evidence 中说明疑点。
5. 看不到视频动态、听不到声音时，依据技术参数、关键帧和文本推断，并在 evidence 中注明「推断」。
6. 参考材料里有产品原图时，凡涉及产品的判断都要拿画面与原图逐项比对（外形、颜色、包装文字、Logo、用法）。
7. JSON 字符串里引用原文请用「」，不要用英文双引号。""")
    dim_ids = ", ".join(d["id"] for d in mine) or "（无，输出空数组）"
    red_rule = f"redlines 必须覆盖 R1–R{len(s['redlines'])}" if panel.get("redlines") else "redlines 输出空数组"
    parts.append(f"""## 输出格式
只输出一个 JSON 对象：
{{{{
  "dimensions": [{{{{"id": "维度ID", "evidence": "具体证据", "score": 1-5 的整数, "issues": ["问题"], "suggestions": ["改法"]}}}}],
  "redlines": [{{{{"id": "R1", "hit": true/false, "evidence": "证据或疑点"}}}}],
  "highlights": ["你负责范围内做得好的地方"],
  "top_fixes": ["你负责范围内最重要的修改建议，最多 3 条"],
  "summary": "50 字以内"
}}}}
dimensions 必须且只能包含：{dim_ids}；{red_rule}。""".replace("{{", "{").replace("}}", "}"))
    return "\n\n".join(parts)


def stage_panels(stage, rubric):
    """评审团编制：rubrics.json 里配置了 panels 就用它；否则每个维度一位评审员，外加一位合规评审员。"""
    s = rubric["stages"][stage]
    panels = s.get("panels") or [
        *({"id": d["id"], "name": d["name"], "role": f"只评「{d['name']}」。", "dimensions": [d["id"]]} for d in s["dimensions"]),
        {"id": "compliance", "name": "合规", "role": "只判断红线。", "dimensions": [], "redlines": True}]
    covered = {i for p in panels for i in p.get("dimensions", [])}
    missing = [d["id"] for d in s["dimensions"] if d["id"] not in covered]
    if missing or not any(p.get("redlines") for p in panels):
        raise ValueError(f"{stage} 的 panels 配置不完整：未覆盖维度 {missing} 或没有负责红线的评审员")
    return panels


def file_to_text_block(path):
    text = Path(path).read_text(errors="replace")
    return {"type": "text", "text": f"\n===== 文件：{Path(path).name} =====\n{text}"}


def image_block(path):
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def image_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return f"{im.width}x{im.height}，格式 {im.format}"
    except Exception:
        return "未知"


def build_user_content(files, context, transcript, frames, platform_hint, tmpdir):
    content = [{"type": "text", "text": "以下是待评审材料。"}]
    tech = None
    for c in context or []:
        if Path(c).suffix.lower() in IMAGE_EXT:
            content.append({"type": "text", "text": f"\n【参考图片：{Path(c).name}（如产品原图、品牌规范），用于比对一致性】"})
            content.append(image_block(c))
            continue
        content.append({"type": "text", "text": "\n【参考材料：前序关卡已通过的内容，用于对照还原度】"})
        content.append(file_to_text_block(c))
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in IMAGE_EXT:
            content.append({"type": "text", "text": f"\n===== 图片：{Path(f).name}（程序测量尺寸：{image_size(f)}）====="})
            content.append(image_block(f))
        elif ext in VIDEO_EXT:
            tech = probe_video(f)
            content.append({"type": "text", "text": f"\n===== 成片：{Path(f).name} =====\n【程序测量的技术参数】\n"
                            + json.dumps(tech, ensure_ascii=False, indent=2)
                            + f"\n【平台参考】{platform_hint}"})
            for t, img in extract_frames(f, tech.get("时长(秒)", 0), frames, tmpdir):
                content.append({"type": "text", "text": f"关键帧 @ {t:.2f}s"})
                content.append(image_block(img))
        else:
            content.append(file_to_text_block(f))
    if transcript:
        content.append({"type": "text", "text": "\n【台词/字幕文本】"})
        content.append(file_to_text_block(transcript))
    return content, tech


# ---------- 调用与聚合 ----------

class call_slot:
    """跨进程限流：同一台机器上所有评审任务合计最多 REVIEW_MAX_CALLS 个模型调用同时进行（默认 10）。
    网站每个任务是独立进程、panel 模式一个任务又会并发多位评审员，接口网关按 Key 限制并发（约 15 个），不限会被 429。"""

    def __enter__(self):
        import fcntl
        import random
        n = max(1, int(env_value("REVIEW_MAX_CALLS") or 10))
        locks = HERE / ".call-slots"
        locks.mkdir(exist_ok=True)
        while True:
            for i in random.sample(range(n), n):
                f = open(locks / f"slot{i}", "w")
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.f = f
                    return self
                except OSError:
                    f.close()
            time.sleep(0.3 + random.random() * 0.5)

    def __exit__(self, *exc):
        self.f.close()  # 关闭即释放锁；进程异常退出时系统也会释放


def call_model(key, model, system, content, effort, retries=3):
    import random
    body = {"model": model, "temperature": 0.2, "max_tokens": 8000, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    if effort:
        body["reasoning_effort"] = effort
    attempt = busy = 0
    while attempt < retries:
        try:
            req = urllib.request.Request(api_url(), data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            with call_slot():
                resp = json.loads(urllib.request.urlopen(req, timeout=600).read())
            text = resp["choices"][0]["message"]["content"]
            return json.JSONDecoder(strict=False).raw_decode(text[text.find("{"):])[0], resp.get("usage", {})
        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
            detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else e
            if isinstance(e, urllib.error.HTTPError) and (e.code in (401, 402) or "Insufficient Balance" in str(detail)):
                raise RuntimeError(f"API 鉴权或余额问题，停止重试：{detail}")
            # 网关忙（429）不算失败次数，等一会儿再试，最多等约 5 分钟
            if isinstance(e, urllib.error.HTTPError) and e.code == 429 and busy < 12:
                busy += 1
                time.sleep(min(60, 5 * busy) + random.random() * 5)
                continue
            attempt += 1
            print(f"  第 {attempt} 次调用失败：{detail}", file=sys.stderr)
            time.sleep(2 ** attempt)
    raise RuntimeError("模型调用连续失败")


def aggregate(stage, rubric, runs):
    s = rubric["stages"][stage]
    rules = rubric["verdict_rules"]
    dims = []
    for d in s["dimensions"]:
        per_run = [next((x for x in r["dimensions"] if x.get("id") == d["id"]), None) for r in runs]
        scores = [int(x["score"]) for x in per_run if x and str(x.get("score", "")).isdigit()]
        best = per_run[0] or {}
        dims.append({**d, "scores": scores,
                     "mean": round(statistics.mean(scores), 2) if scores else None,
                     "spread": max(scores) - min(scores) if scores else None,
                     "evidence": best.get("evidence", ""),
                     "issues": best.get("issues", []), "suggestions": best.get("suggestions", [])})
    redlines = []
    for i, text in enumerate(s["redlines"]):
        rid = f"R{i + 1}"
        hits = [x for r in runs for x in r.get("redlines", []) if x.get("id") == rid]
        n_hit = sum(1 for x in hits if x.get("hit") is True)
        status = "命中" if n_hit * 2 > len(runs) else "疑似（需人审）" if n_hit else "未命中"
        ev = next((x.get("evidence", "") for x in hits if x.get("hit")), hits[0].get("evidence", "") if hits else "")
        redlines.append({"id": rid, "text": text, "status": status, "hits": f"{n_hit}/{len(runs)}", "evidence": ev})

    scored = [d for d in dims if d["mean"] is not None]
    total = round(sum(d["mean"] * d["weight"] for d in scored) / sum(d["weight"] for d in scored), 2) if scored else 0
    min_dim = min((d["mean"] for d in scored), default=0)
    if any(r["status"] == "命中" for r in redlines):
        verdict = "驳回（命中红线）"
    elif total >= rules["pass"]["min_score"] and min_dim >= rules["pass"]["min_dimension"]:
        verdict = "通过"
    elif total >= rules["revise"]["min_score"] and min_dim >= rules["revise"]["min_dimension"]:
        verdict = "修改后通过"
    else:
        verdict = "驳回"
    needs_human = [d["id"] for d in dims if (d["spread"] or 0) >= 2] + \
                  [r["id"] for r in redlines if r["status"].startswith("疑似")]
    return {"stage": s["name"], "total": total, "min_dimension": min_dim, "verdict": verdict,
            "needs_human_review": needs_human, "dimensions": dims, "redlines": redlines,
            "highlights": runs[0].get("highlights", []), "top_fixes": runs[0].get("top_fixes", []),
            "summary": runs[0].get("summary", "")}


def render_markdown(result, tech, args, usage):
    L = [f"# {result['stage']}报告", "",
         f"- 评审对象：{', '.join(Path(f).name for f in args.files)}",
         f"- 模型：{args.model} × {args.runs} 次采样" + ("（分维度评审团：" + "、".join(p["name"] for p in result["panels"]) + "）" if result.get("panels") else "") + f" · {datetime.now():%Y-%m-%d %H:%M}",
         f"- **结论：{result['verdict']}** · 加权总分 **{result['total']}** / 5 · 最低维度 {result['min_dimension']}"]
    if result["needs_human_review"]:
        L.append(f"- ⚠ 需人工复核：{', '.join(result['needs_human_review'])}（多次采样分歧 ≥ 2 分或疑似红线）")
    L += ["", f"> {result['summary']}", ""]
    if tech:
        L += ["## 技术参数（程序测量）", "", "| 指标 | 值 |", "|---|---|"]
        L += [f"| {k} | {', '.join(v) if isinstance(v, list) else v or '无'} |" for k, v in tech.items()]
        L.append("")
    L += ["## 红线检查", "", "| ID | 红线 | 结果 | 命中次数 | 证据/疑点 |", "|---|---|---|---|---|"]
    L += [f"| {r['id']} | {r['text']} | {r['status']} | {r['hits']} | {r['evidence']} |" for r in result["redlines"]]
    L += ["", "## 维度评分", "", "| ID | 维度 | 权重 | 均分 | 各次得分 |", "|---|---|---|---|---|"]
    L += [f"| {d['id']} | {d['name']} | {int(d['weight'] * 100)}% | {d['mean']} | {d['scores']} |" for d in result["dimensions"]]
    L += ["", "## 优先修改", ""] + [f"{i + 1}. {x}" for i, x in enumerate(result["top_fixes"])]
    L += ["", "## 亮点", ""] + [f"- {x}" for x in result["highlights"]]
    L += ["", "## 维度详情", ""]
    for d in result["dimensions"]:
        L += [f"### {d['id']} {d['name']} — {d['mean']} 分", "", f"**证据**：{d['evidence']}", ""]
        L += [f"- 问题：{x}" for x in d["issues"]] + [f"- 建议：{x}" for x in d["suggestions"]] + [""]
    L += ["---", f"Token 用量：{usage}"]
    return "\n".join(L)


DEFAULT_PLATFORM_HINT = "短视频信息流（抖音/视频号），竖屏 9:16 1080x1920，响度参考 -14～-16 LUFS，真峰值 ≤ -1 dBTP"


def merge_panels(outs):
    """把同一轮里各评审员的输出拼成一份完整评审（维度、红线各取负责人的）。"""
    merged = {"dimensions": [], "redlines": [], "highlights": [], "top_fixes": [], "summary": ""}
    notes = []
    for panel, o in outs:
        merged["dimensions"] += [d for d in o.get("dimensions", []) if d.get("id") in panel.get("dimensions", [])]
        if panel.get("redlines"):
            merged["redlines"] += o.get("redlines", [])
        merged["highlights"] += o.get("highlights", [])[:2]
        # 合规问题排在最前：红线不改，其余修改都没有意义
        fixes = o.get("top_fixes", [])[:2]
        merged["top_fixes"] = fixes + merged["top_fixes"] if panel.get("redlines") else merged["top_fixes"] + fixes
        if o.get("summary"):
            notes.append(f"【{panel['name']}】{o['summary']}")
    merged["summary"] = " ".join(notes)
    return merged


def evaluate(stage, files, context=None, transcript=None, runs=3, model=None, effort="high",
             frames=12, platform_hint=DEFAULT_PLATFORM_HINT, rubric_path=HERE / "rubrics.json", key=None, mode="sample"):
    """供批量调用：返回 {result, tech, raw_runs, usage, model, mode}。"""
    key = key or load_api_key()
    model = model or default_model()
    rubric = json.loads(Path(rubric_path).read_text())
    if mode == "panel":
        panels = stage_panels(stage, rubric)
        calls = [(r, p, build_system_prompt(stage, rubric, p)) for r in range(runs) for p in panels]
    else:
        calls = [(r, None, build_system_prompt(stage, rubric)) for r in range(runs)]
    with tempfile.TemporaryDirectory() as tmp:
        content, tech = build_user_content(files, context, transcript, frames, platform_hint, tmp)
        with ThreadPoolExecutor(min(len(calls), 12)) as pool:
            outs = list(pool.map(lambda c: call_model(key, model, c[2], content, effort), calls))
    usage = {k: sum(o[1].get(k, 0) for o in outs) for k in ("prompt_tokens", "completion_tokens")}
    if mode == "panel":
        raw = [merge_panels([(c[1], o[0]) for c, o in zip(calls, outs) if c[0] == r]) for r in range(runs)]
    else:
        raw = [o[0] for o in outs]
    result = aggregate(stage, rubric, raw)
    if mode == "panel":
        result["panels"] = [{"id": p["id"], "name": p["name"], "dimensions": p.get("dimensions", []), "redlines": bool(p.get("redlines"))}
                            for p in panels]
    return {"result": result, "tech": tech, "raw_runs": raw, "usage": usage, "model": model, "mode": mode}


def main():
    ap = argparse.ArgumentParser(description="视频全链路 LLM 评审")
    ap.add_argument("stage", choices=["creative", "storyboard", "asset", "video"])
    ap.add_argument("files", nargs="+", help="待评审文件：文本(.md/.txt/.srt…)、图片、视频")
    ap.add_argument("--context", nargs="*", help="前序关卡材料（如 brief、分镜），用于对照还原度")
    ap.add_argument("--transcript", help="成片台词/字幕文本")
    ap.add_argument("--runs", type=int, default=3, help="采样次数，默认 3")
    ap.add_argument("--frames", type=int, default=12, help="成片在前 3 秒之外均匀抽取的帧数")
    ap.add_argument("--model", default=None, help="默认取 REVIEW_MODEL，未设置时为 deepseek-flash")
    ap.add_argument("--mode", choices=["sample", "panel"], default="sample", help="sample：整套标准多次采样；panel：分维度评审团")
    ap.add_argument("--effort", choices=["low", "high", "max"], default="high")
    ap.add_argument("--platform-hint", default=DEFAULT_PLATFORM_HINT)
    ap.add_argument("--rubric", default=str(HERE / "rubrics.json"))
    ap.add_argument("--out", default=str(HERE / "reports"))
    args = ap.parse_args()

    args.model = args.model or default_model()
    print(f"[{args.stage}] {args.mode} · {args.runs} 次 · {args.model} …", file=sys.stderr)
    ev = evaluate(args.stage, args.files, args.context, args.transcript, args.runs, args.model, args.effort,
                  args.frames, args.platform_hint, args.rubric, mode=args.mode)
    result, tech, runs, usage = ev["result"], ev["tech"], ev["raw_runs"], ev["usage"]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.stage}_{Path(args.files[0]).stem}_{datetime.now():%Y%m%d_%H%M%S}"
    (out / f"{stem}.json").write_text(json.dumps({"result": result, "tech": tech, "raw_runs": runs}, ensure_ascii=False, indent=2))
    (out / f"{stem}.md").write_text(render_markdown(result, tech, args, usage))
    print(f"结论：{result['verdict']} · 总分 {result['total']} · 报告：{out / stem}.md")


if __name__ == "__main__":
    main()
