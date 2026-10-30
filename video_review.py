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
import hashlib
import http.client
import json
import mimetypes
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
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
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            k, sep, v = line.partition("=")
            if sep and k.strip() == name:
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                return v or None
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
    m = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err)
    if not m:
        # 文件不存在、为空、损坏或只有音轨：不再继续测量，免得返回残缺参数（如误导性的「无音轨」）
        last = next((l.strip() for l in reversed(err.splitlines()) if l.strip()), "")
        return {"错误": f"无法读取视频流：{last[-200:] or '未知错误'}", **info}
    w, h = int(m[2]), int(m[3])
    # 手机竖拍常编码成横向 + 旋转元数据，按显示方向报分辨率
    rot = re.search(r"rotation of (-?[\d.]+) degrees", err) or re.search(r"rotate\s*:\s*(-?\d+)", err)
    if rot and round(abs(float(rot[1]))) % 180 == 90:
        w, h = h, w
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

    # 冻结要在原分辨率上测：缩小后噪点被抹平，静止字卡上的正常画面也会被当成冻结
    err = run_ffmpeg(["-i", str(path), "-an", "-vf", "blackdetect=d=0.2:pix_th=0.10,freezedetect=n=0.003:d=0.5", "-f", "null", "-"])
    info["黑帧区间"] = [f"{a}s–{b}s" for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]
    starts = re.findall(r"freeze_start: ([\d.]+)", err)
    durs = [float(d) for d in re.findall(r"freeze_duration: ([\d.]+)", err)] + [None] * len(starts)  # 冻到结尾没有 duration
    info["冻结帧起点"] = [f"{t}s" for t, d in zip(starts, durs) if d is None or d >= 1.0]
    info["短静止(0.5–1秒)"] = [f"{round(float(t), 2)}s" for t, d in zip(starts, durs) if d is not None and d < 1.0]
    info.update(picture_stats(path))
    return info


def picture_stats(path):
    """画面统计（按 5fps、320 宽采样，30 秒成片约 1 秒）：模型看缩小后的关键帧分不出细的画质问题，由程序量出来。

    - 模糊度：blurdetect 均值，越大越糊。清晰的成片约 4–5，高斯模糊 σ=6 约 7–10
    - 亮度：Y 均值 0–255，过暗 < 40、过曝 > 210
    - 场景切换：相邻帧变化大的时间点，用于抽帧
    0.5–1 秒的短静止在 probe_video 里按原分辨率测。
    """
    err = run_ffmpeg(["-i", str(path), "-an", "-vf",
                      "fps=5,scale=320:-2,blurdetect=block_width=16:block_height=16,"
                      "signalstats,select='gte(scene,0)',metadata=mode=print", "-f", "null", "-"])
    out = {}
    if m := re.findall(r"blur mean: ([\d.]+)", err):
        out["模糊度"] = round(float(m[-1]), 2)
    if y := [float(x) for x in re.findall(r"signalstats\.YAVG=([\d.]+)", err)]:
        out["平均亮度(0-255)"] = round(sum(y) / len(y), 1)
    times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]
    scores = [float(x) for x in re.findall(r"lavfi\.scene_score=([\d.]+)", err)]
    # 前 0.5 秒不算：编码器起始帧常有跳变，且钩子段本来就每 0.5 秒一帧
    out["场景切换(秒)"] = [round(t, 2) for t, s in zip(times, scores) if s >= SCENE_THRESHOLD and t >= 0.5]
    return out


SCENE_THRESHOLD = 0.05  # 5fps / 320 宽下的场景变化分；合成成片的硬切约 0.06–0.10，渐变不到 0.02


MAX_FRAMES = 40  # 单个视频最多送给模型的帧数
MAX_GAP = 1.0  # 3 秒后相邻两帧的最大间隔（秒），帧数到上限时放宽


def frame_times(duration, n, scenes=()):
    """抽帧时间表：前 3 秒每 0.5 秒一帧（看钩子）；3 秒后均匀 n 帧（段中点）+ 每个场景切换后 0.1 秒；
    再在间隔超过 MAX_GAP 的地方补帧；尾帧 duration-0.1（CTA）。总数不超过 MAX_FRAMES，超了先删补帧、再删场景帧。"""
    hook = [t / 2 for t in range(0, 6) if t / 2 < duration]
    tail = max(duration - 0.1, 0)
    base = []
    if duration > 3 and n > 0:
        step = (duration - 3) / n
        base = [round(3 + step * (i + 0.5), 2) for i in range(n)]
    cuts = [round(min(s + 0.1, tail), 2) for s in scenes if 3 <= s < duration]
    fixed = sorted(set(hook + base + [tail]))
    room = max(MAX_FRAMES - len(fixed), 0)
    if len(cuts) > room:  # 场景太多：均匀保留一部分
        cuts = [cuts[round(i * (len(cuts) - 1) / max(room - 1, 1))] for i in range(room)] if room else []
    times = sorted(set(fixed + cuts))
    fill = []
    if n > 0:
        later = [t for t in times if t >= 2.5]
        for a, b in zip(later, later[1:]):
            k = int((b - a) / MAX_GAP - 1e-9)
            fill += [round(a + (b - a) * j / (k + 1), 2) for j in range(1, k + 1)]
    room = MAX_FRAMES - len(times)
    if len(fill) > room:
        fill = [fill[round(i * (len(fill) - 1) / max(room - 1, 1))] for i in range(room)] if room > 0 else []
    return sorted(set(times + fill)), tail


def extract_frames(path, duration, n, outdir, scenes=()):
    """按 frame_times 抽帧，返回 [(时间, 图片路径)]。"""
    times, tail = frame_times(duration, n, scenes)
    frames = []
    for t in times:
        out = Path(outdir) / f"frame_{t:07.2f}.jpg"
        subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", str(t), "-i", str(path),
                        "-frames:v", "1", "-vf", "scale='min(768,iw)':-2", "-q:v", "3", "-y", str(out)])
        if out.exists():
            frames.append((t, out))
    if frames and Path(path).is_file() and not any(t == tail for t, _ in frames):
        # duration 是容器时长，音轨比视频长时尾帧时间点超出了视频流：解码到视频流末尾，保留最后一帧
        out = Path(outdir) / "frame_tail.jpg"
        p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path), "-map", "0:v:0", "-vf", "scale='min(768,iw)':-2",
                            "-q:v", "3", "-update", "1", "-y", str(out)], capture_output=True, text=True, errors="replace")
        if out.exists() and (m := re.findall(r"time=(\d+):(\d+):([\d.]+)", p.stderr)):
            h, mi, sec = m[-1]
            frames.append((round(max(int(h) * 3600 + int(mi) * 60 + float(sec) - 0.1, 0), 2), out))
    return frames


# ---------- Prompt ----------

# B 层评测发现的判断偏差（REPORT_B §5）对应的补充规则，sample 与 panel 两种提示词共用
JUDGING_RULES = """## 判断细则
- 画面类维度（画面质量、视觉质量、技术规格、开场吸引力等）只依据关键帧、图片和【程序测量】打分。文字材料（审片记录、字幕、说明）里对画面的描述不能作为加分或扣分的依据；与画面不一致时写进 issues，标「待人工核实」。
- 【程序测量】是程序算出的客观数值，优先于你对缩小图片的观感：清晰度低、模糊度高、亮度过暗或过曝，都要在对应维度如实扣分。
- 「短静止(0.5–1秒)」只说明这段画面没有变化：字卡、落版、定格是正常设计，不算冻结帧；只有对照关键帧确认那里本该有动作（如动作中途卡住）时才算技术问题，并写进 evidence。
- 图片和关键帧上的产品名、品牌名、包装文字、价格，以「程序识别的文字」为准，与 brief / 资产清单 / 分镜里的写法逐字比对（含形近字，如「守望」与「守旺」）；有一个字不同就是信息错误。OCR 可能把正确的字识别错，拿不准时对照图片本身，并在 evidence 中写明。
- 极限用语与夸大承诺只管：绝对化用语（最、第一、顶级等）、保证效果或功效断言、无依据的比较和数据。普通的卖点描述、情绪化表达（如「好喝到停不下来」）不算。
- 要理解含义才能判断的违规也要逐条检查：与品牌价值观或 brief 的调性、受众逐条对照；诱导互动（抽奖、点赞领奖）、站外引流（二维码、外部账号、联系方式）；公益提醒、安全警示等反面示范不算违规。
- 篇幅、套话、排版不影响打分：同样的内容写得更长、加了客套话，分数不变。"""


def build_system_prompt(stage, rubric, panel=None):
    """panel 为空时评整套标准；否则只评 panel["dimensions"]，panel["redlines"] 为真时才判红线。"""
    s = rubric["stages"][stage]
    if panel:
        return build_panel_prompt(stage, rubric, panel)
    dims = "\n".join(
        f"- {d['id']} {d['name']}（权重 {round(d['weight'] * 100)}%）：{d['criteria']}\n"
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

{JUDGING_RULES}

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
    parts.append(JUDGING_RULES)
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


def read_text_file(path):
    """按 BOM / UTF-8 / GB18030 解码；二进制文件（含 NUL 字节，如 docx、pdf）直接报错，不把乱码送进模型。"""
    raw = Path(path).read_bytes()
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if raw.startswith(bom):
            return raw.decode(enc).replace("\r\n", "\n")
    if b"\x00" in raw:
        raise ValueError(f"{Path(path).name} 不是文本文件，请转成 .md / .txt 再提交")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc).replace("\r\n", "\n")
        except UnicodeDecodeError:
            pass
    raise ValueError(f"{Path(path).name} 的编码无法识别，请另存为 UTF-8")


def file_to_text_block(path):
    # 材料里以 ===== 开头的行会被读成文件边界，改成全角，防止伪造「另一份文件」（提示词注入）
    text = re.sub(r"^=====", "＝＝＝＝＝", read_text_file(path), flags=re.M)
    return {"type": "text", "text": f"\n===== 文件：{Path(path).name} =====\n{text}"}


def image_block(path):
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


_OCR = None
_OCR_CACHE = {}  # 文件内容 sha1 → 识别结果：同一素材、同一帧在不同用例 / 多次评审里只识别一次
OCR_THREADS = int(os.environ.get("VR_OCR_THREADS", "2"))  # 默认会占满全部核，32 核机器上反而慢 10 倍
_OCR_LOCK = threading.Lock()  # 批量评测多线程并发：模型只加载一次


def _load_ocr():
    global _OCR
    with _OCR_LOCK:
        if _OCR is not None:
            return _OCR
        try:
            import onnxruntime
            import rapidocr_onnxruntime.utils as ocr_utils

            class Opts(onnxruntime.SessionOptions):
                def __init__(self):
                    super().__init__()
                    self.intra_op_num_threads = OCR_THREADS
                    self.inter_op_num_threads = 1

            ocr_utils.SessionOptions = Opts  # rapidocr 1.2.x 没有线程参数，只能替换它建会话时用的类
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        except ImportError:
            _OCR = False
    return _OCR


def ocr_text(path, min_conf=0.5):
    """本地 OCR 读出图上文字（rapidocr-onnxruntime）。没装时返回 None，评审照常进行，只是少一项程序证据。"""
    if not _load_ocr():
        return None
    try:
        key = hashlib.sha1(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None
    if key not in _OCR_CACHE:
        try:
            res, _ = _OCR(str(path))
        except Exception:
            return None
        _OCR_CACHE[key] = [t for _, t, c in res or [] if float(c) >= min_conf and t.strip()]
    return list(_OCR_CACHE[key])


def _thumb(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            g = im.convert("L")
            g.thumbnail((160, 160))
            return g
    except Exception:
        return None


def same_picture(a, b):
    """两张缩略图几乎一样（编码噪声级别）：差值 > 24 的像素不到 0.2%。实测同一镜头相邻帧为 0，换镜、闪帧 ≥ 3%。"""
    if a is None or b is None or a.size != b.size:
        return False
    from PIL import ImageChops
    h = ImageChops.difference(a, b).histogram()
    return sum(h[25:]) < 0.002 * sum(h)


def frames_ocr(paths):
    """关键帧逐帧 OCR，画面和上一张识别过的帧几乎一样时直接沿用结果。"""
    out, last, words = [], None, None
    for p in paths:
        th = _thumb(p)
        if words is None or not same_picture(th, last):
            words, last = ocr_text(p), th
        out.append(words)
    return out


def image_sharpness(path):
    """边缘强度方差（缩到 768 内后计算）：越小越糊。合成主视觉清晰时约 1000–1900，高斯模糊后约 200–300。"""
    try:
        from PIL import Image, ImageFilter, ImageStat
        with Image.open(path) as im:
            g = im.convert("L")
            g.thumbnail((768, 768))
            return round(ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0])
    except Exception:
        return None


def image_facts(path):
    """附在图片标题后的程序测量：清晰度与 OCR 文字。模型核对产品名、包装文字时以 OCR 为准逐字比对。"""
    parts = []
    if (sh := image_sharpness(path)) is not None:
        parts.append(f"清晰度（边缘方差，越小越糊；清晰的设计稿通常 > 800）{sh}")
    words = ocr_text(path)
    if words is not None:
        parts.append("程序识别的图上文字：" + (" / ".join(words) if words else "无"))
    return "\n【程序测量】" + "；".join(parts) if parts else ""


def image_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return f"{im.width}x{im.height}，格式 {im.format}"
    except Exception:
        return "未知"


def build_user_content(files, context, transcript, frames, platform_hint, tmpdir):
    content = [{"type": "text", "text": "以下是待评审材料。"}]
    techs = {}
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
            content.append({"type": "text", "text": f"\n===== 图片：{Path(f).name}（程序测量尺寸：{image_size(f)}）====="
                            + image_facts(f)})
            content.append(image_block(f))
        elif ext in VIDEO_EXT:
            info = probe_video(f)
            if "错误" in info:
                raise ValueError(f"{Path(f).name}：{info['错误']}")
            techs[Path(f).name] = info
            content.append({"type": "text", "text": f"\n===== 成片：{Path(f).name} =====\n【程序测量的技术参数】\n"
                            + json.dumps(info, ensure_ascii=False, indent=2)
                            + f"\n【平台参考】{platform_hint}"})
            sub = Path(tmpdir) / f"v{len(techs)}"  # 每个视频单独目录，同名帧不互相覆盖
            sub.mkdir(exist_ok=True)
            shots = extract_frames(f, info.get("时长(秒)", 0), frames, sub, info.get("场景切换(秒)", ()))
            seen = set()
            # 关键帧上的文字（字幕、包装、落版）也 OCR；画面没变的帧沿用上一帧结果，相同的一组文字不重复列出
            for (t, img), words in zip(shots, frames_ocr([p for _, p in shots])):
                words = words or []
                note = f"（程序识别的画面文字：{' / '.join(words)}）" if words and tuple(words) not in seen else ""
                seen.add(tuple(words))
                content.append({"type": "text", "text": f"关键帧 @ {t:.2f}s{note}"})
                content.append(image_block(img))
        else:
            content.append(file_to_text_block(f))
    if transcript:
        content.append({"type": "text", "text": "\n【台词/字幕文本】"})
        content.append(file_to_text_block(transcript))
    # 一个视频时直接返回它的参数；多个视频时按文件名分开，不互相覆盖
    tech = None if not techs else next(iter(techs.values())) if len(techs) == 1 else techs
    return content, tech


# ---------- 调用与聚合 ----------

def _try_lock(f):
    """非阻塞独占锁，拿不到抛 OSError。Linux 用 flock，Windows 用 msvcrt（锁文件第一个字节）。"""
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)


class call_slot:
    """跨进程限流：同一台机器上所有评审任务合计最多 REVIEW_MAX_CALLS 个模型调用同时进行（默认 10）。
    网站每个任务是独立进程、panel 模式一个任务又会并发多位评审员，接口网关按 Key 限制并发（约 15 个），不限会被 429。"""

    def __enter__(self):
        import random
        n = max(1, int(env_value("REVIEW_MAX_CALLS") or 10))
        locks = HERE / ".call-slots"
        locks.mkdir(exist_ok=True)
        while True:
            for i in random.sample(range(n), n):
                f = open(locks / f"slot{i}", "a+b")
                try:
                    _try_lock(f)
                    self.f = f
                    return self
                except OSError:
                    f.close()
            time.sleep(0.3 + random.random() * 0.5)

    def __exit__(self, *exc):
        self.f.close()  # 关闭即释放锁；进程异常退出时系统也会释放


class BadOutput(ValueError):
    """模型返回了，但内容不能用：choices 为空、content 为空、没有 JSON 对象、缺 dimensions / redlines。"""


def parse_output(resp):
    try:
        text = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise BadOutput(f"响应结构不完整：{str(resp)[:200]}")
    if not isinstance(text, str) or not text.strip():
        raise BadOutput("模型返回了空内容")
    # 从每个 { 依次尝试：模型在 JSON 前的说明文字里也可能出现 {
    dec = json.JSONDecoder(strict=False)
    for m in re.finditer(r"\{", text):
        try:
            obj = dec.raw_decode(text, m.start())[0]
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("dimensions"), list) and isinstance(obj.get("redlines"), list):
            return obj
    if resp["choices"][0].get("finish_reason") == "length":
        raise BadOutput(f"输出达到 max_tokens 上限（{MAX_TOKENS}，含思考）被截断：…{text[-120:]}")
    raise BadOutput(f"输出里没有包含 dimensions 和 redlines 的 JSON 对象：{text[:200]}")


# 输出上限含思考 token：成片关 20+ 帧时思考约 4–8k、JSON 约 3k，8000 会截断
MAX_TOKENS = 16000


def call_model(key, model, system, content, effort, retries=3):
    import random
    body = {"model": model, "temperature": 0.2, "max_tokens": MAX_TOKENS, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    if effort == "off":
        body["thinking"] = {"type": "disabled"}  # 关掉思考：deepseek-flash 单次从约 6 秒降到 1–2 秒
    elif effort:
        body["reasoning_effort"] = effort
    attempt = busy = 0
    while attempt < retries:
        try:
            req = urllib.request.Request(api_url(), data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            with call_slot():
                resp = json.loads(urllib.request.urlopen(req, timeout=600).read())
            usage = resp.get("usage", {}) if isinstance(resp, dict) else {}
            return parse_output(resp), usage
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, json.JSONDecodeError, BadOutput) as e:
            detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else e
            if isinstance(e, urllib.error.HTTPError) and (e.code in (401, 402) or "Insufficient Balance" in str(detail)):
                raise RuntimeError(f"API 鉴权或余额问题，停止重试：{detail}")
            # 有的模型不接受某些可选参数（如 claude-sonnet-5-5 不允许改 temperature）：去掉被点名的参数再试，不计失败次数
            if isinstance(e, urllib.error.HTTPError) and e.code == 400:
                bad = next((k for k in ("temperature", "reasoning_effort", "thinking", "response_format") if k in body and k in str(detail)), None)
                if bad:
                    body.pop(bad)
                    continue
            # 网关忙不算失败次数，等一会儿再试，最多等约 5 分钟：429 并发超限；「All available accounts exhausted」是网关上游账号暂时用尽
            # 但「accounts exhausted」常常持续很久：只等 3 次（约半分钟）就放弃，让调用方换模型
            exhausted = "accounts exhausted" in str(detail)
            if isinstance(e, urllib.error.HTTPError) and (e.code == 429 or exhausted) and busy < (3 if exhausted else 12):
                busy += 1
                time.sleep(min(60, 5 * busy) + random.random() * 5)
                continue
            if exhausted:
                raise RuntimeError(f"评审模型 {model} 暂时不可用（接口上游账号用尽），请换一个模型")
            attempt += 1
            print(f"  第 {attempt} 次调用失败：{detail}", file=sys.stderr)
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError("模型调用连续失败")


def parse_score(v):
    """1–5 的整数分：接受 4、4.0、"4"、"4.0"；小数、越界、文字分返回 None（转人审，不静默计入或丢弃）。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        try:
            v = float(v.strip())
        except ValueError:
            return None
    if isinstance(v, (int, float)) and float(v).is_integer() and 1 <= v <= 5:
        return int(v)
    return None


def parse_hit(v):
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "是", "命中")
    return v is True or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 1)


# 框架文档 6.3：成片只能从关键帧和测量值推断时间维度，画面质量（V3）与声音质量（V4）的结论必须人审
ALWAYS_HUMAN = {"video": ("V3", "V4")}
REJECT_REVIEW = "驳回复核"  # 框架文档第 5 节：机审驳回转法务 / 品牌复核
BORDERLINE_REVIEW = "及格线附近"
BORDERLINE = (2.8, 3.2)  # rubrics.json 的 verdict_rules.borderline.total 可覆盖


def aggregate(stage, rubric, runs):
    s = rubric["stages"][stage]
    rules = rubric["verdict_rules"]
    runs = [r if isinstance(r, dict) else {} for r in runs]
    reasons = {}  # 需人审的项 → 原因

    def flag(k, why):
        reasons.setdefault(k, why)

    dims = []
    for d in s["dimensions"]:
        per_run = [next((x for x in r.get("dimensions") or [] if isinstance(x, dict) and x.get("id") == d["id"]), None) for r in runs]
        parsed = [parse_score(x.get("score")) if x else None for x in per_run]
        scores = [p for p in parsed if p is not None]
        mean = round(statistics.mean(scores), 2) if scores else None
        # 证据取分数最接近均分的那次采样，避免与均分矛盾（如 3 次里只有 1 次给了 1 分时引用那次的证据）
        cands = [(x, p) for x, p in zip(per_run, parsed) if x and p is not None]
        best = min(cands, key=lambda c: abs(c[1] - mean))[0] if cands else next((x for x in per_run if x), {})
        if len(scores) < len(runs):
            bad = len([x for x in per_run if x]) - len(scores)
            flag(d["id"], f"{len(runs) - len(scores)}/{len(runs)} 次采样没有有效分数" + (f"（{bad} 次不是 1–5 的整数）" if bad else ""))
        dims.append({**d, "scores": scores, "mean": mean, "_exact": statistics.mean(scores) if scores else None,
                     "spread": max(scores) - min(scores) if scores else None,
                     "evidence": best.get("evidence", ""),
                     "issues": best.get("issues", []), "suggestions": best.get("suggestions", [])})
        if scores and dims[-1]["spread"] >= 2:
            flag(d["id"], f"多次采样分歧 {dims[-1]['spread']} 分")

    redlines = []
    for i, text in enumerate(s["redlines"]):
        rid = f"R{i + 1}"
        per_run = [[x for x in r.get("redlines") or [] if isinstance(x, dict) and x.get("id") == rid] for r in runs]
        hits = [x for xs in per_run for x in xs]
        n_hit = sum(1 for xs in per_run if any(parse_hit(x.get("hit")) for x in xs))  # 同一次采样重复列出只算一票
        n_judged = sum(1 for xs in per_run if xs)
        status = "命中" if n_hit * 2 > len(runs) else "疑似（需人审）" if n_hit else "未命中"
        ev = next((x.get("evidence", "") for x in hits if parse_hit(x.get("hit"))), hits[0].get("evidence", "") if hits else "")
        redlines.append({"id": rid, "text": text, "status": status, "hits": f"{n_hit}/{len(runs)}", "evidence": ev})
        if status == "命中":
            flag(rid, "命中红线，需法务 / 品牌确认")
        elif n_hit:
            flag(rid, f"只有 {n_hit}/{len(runs)} 次采样判命中")
        elif n_judged < len(runs):
            flag(rid, f"{len(runs) - n_judged}/{len(runs)} 次采样没有判断这条红线")

    complete = all(d["mean"] is not None for d in dims)
    scored = [d for d in dims if d["mean"] is not None]
    # 总分始终按全部权重计算：缺失维度不能靠重新归一「藏掉」；缺维度时只出驳回或无法判定，不出通过
    # 判定用未取整的值：2.9967 取整成 3.0 会越过「修改后通过」门槛
    exact = sum(d["_exact"] * d["weight"] for d in scored) / sum(d["weight"] for d in dims) if scored else None
    low = min((d["_exact"] for d in scored), default=None)
    total = round(exact, 2) if scored else None
    min_dim = min((d["mean"] for d in scored), default=None)
    if any(r["status"] == "命中" for r in redlines):
        verdict = "驳回（命中红线）"
    elif not complete:
        verdict = "无法判定（评审输出不完整）"
    elif exact >= rules["pass"]["min_score"] - 1e-9 and low >= rules["pass"]["min_dimension"] - 1e-9:
        verdict = "通过"
    elif exact >= rules["revise"]["min_score"] - 1e-9 and low >= rules["revise"]["min_dimension"] - 1e-9:
        verdict = "修改后通过"
    else:
        verdict = "驳回"
    for k in ALWAYS_HUMAN.get(stage, ()):
        flag(k, "只能从关键帧和测量值推断，结论必须人审")
    # 及格线附近重跑容易翻转结论（B 层：翻转的用例多数总分在 2.85–3.18）
    lo, hi = rules.get("borderline", {}).get("total", BORDERLINE)
    if total is not None and complete and lo <= total <= hi and not verdict.startswith("驳回（命中红线）"):
        flag(BORDERLINE_REVIEW, f"总分 {total} 在 {lo}–{hi} 之间，重新评审可能得出不同结论")
    if verdict.startswith("驳回"):
        flag(REJECT_REVIEW, "机审驳回，需法务 / 品牌复核")

    # 总评与修改建议取总分最接近聚合总分的那次采样（与均分一致的多数意见）
    def run_total(r):
        m = {x.get("id"): parse_score(x.get("score")) for x in r.get("dimensions") or [] if isinstance(x, dict)}
        got = [(m[d["id"]], d["weight"]) for d in s["dimensions"] if m.get(d["id"]) is not None]
        return sum(a * w for a, w in got) / sum(w for _, w in got) if got else None
    rep = min(runs, key=lambda r: abs(run_total(r) - total) if run_total(r) is not None and total is not None else 99) if runs else {}
    for d in dims:
        d.pop("_exact")
    return {"stage": s["name"], "total": total, "min_dimension": min_dim, "verdict": verdict,
            "needs_human_review": list(reasons), "review_reasons": reasons, "dimensions": dims, "redlines": redlines,
            "highlights": rep.get("highlights", []), "top_fixes": rep.get("top_fixes", []),
            "summary": rep.get("summary", "")}


def render_markdown(result, tech, args, usage):
    L = [f"# {result['stage']}报告", "",
         f"- 评审对象：{', '.join(Path(f).name for f in args.files)}",
         f"- 模型：{args.model} × {args.runs} 次采样" + ("（分维度评审团：" + "、".join(p["name"] for p in result["panels"]) + "）" if result.get("panels") else "") + f" · {datetime.now():%Y-%m-%d %H:%M}",
         f"- **结论：{result['verdict']}** · 加权总分 **{result['total']}** / 5 · 最低维度 {result['min_dimension']}"]
    if result["needs_human_review"]:
        reasons = result.get("review_reasons") or {}
        L.append("- ⚠ 需人工复核：" + "；".join(f"{k}（{reasons[k]}）" if k in reasons else k for k in result["needs_human_review"]))
    L += ["", f"> {result['summary']}", ""]

    def cell(v):  # 表格单元格：转义竖线、换行改成 <br>
        return str(v).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")

    def value(v):
        if isinstance(v, list):
            return ", ".join(map(str, v)) or "无"
        return "无" if v is None or v == "" else v

    if tech:
        # 多个视频时 tech 是 {文件名: 参数}
        groups = tech.items() if all(isinstance(v, dict) for v in tech.values()) else [(None, tech)]
        for name, t in groups:
            L += [f"## 技术参数（程序测量）{'：' + name if name else ''}", "", "| 指标 | 值 |", "|---|---|"]
            L += [f"| {cell(k)} | {cell(value(v))} |" for k, v in t.items()]
            L.append("")
    L += ["## 红线检查", "", "| ID | 红线 | 结果 | 命中次数 | 证据/疑点 |", "|---|---|---|---|---|"]
    L += [f"| {r['id']} | {cell(r['text'])} | {r['status']} | {r['hits']} | {cell(r['evidence'])} |" for r in result["redlines"]]
    L += ["", "## 维度评分", "", "| ID | 维度 | 权重 | 均分 | 各次得分 |", "|---|---|---|---|---|"]
    L += [f"| {d['id']} | {cell(d['name'])} | {round(d['weight'] * 100)}% | {d['mean']} | {d['scores']} |" for d in result["dimensions"]]
    L += ["", "## 优先修改", ""] + [f"{i + 1}. {x}" for i, x in enumerate(result["top_fixes"])]
    L += ["", "## 亮点", ""] + [f"- {x}" for x in result["highlights"]]
    L += ["", "## 维度详情", ""]
    for d in result["dimensions"]:
        L += [f"### {d['id']} {d['name']} — {d['mean']} 分", "", f"**证据**：{d['evidence']}", ""]
        L += [f"- 问题：{x}" for x in d["issues"]] + [f"- 建议：{x}" for x in d["suggestions"]] + [""]
    L += ["---", f"Token 用量：{usage}"]
    return "\n".join(L)


def load_rubric(path=HERE / "rubrics.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    rubric = load_rubric(rubric_path)
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
    ap.add_argument("--effort", choices=["off", "low", "high", "max"], default="high")
    ap.add_argument("--platform-hint", default=DEFAULT_PLATFORM_HINT)
    ap.add_argument("--rubric", default=str(HERE / "rubrics.json"))
    ap.add_argument("--out", default=str(HERE / "reports"))
    args = ap.parse_args()
    if args.runs < 1:
        ap.error("--runs 至少为 1")
    if args.frames < 0:
        ap.error("--frames 不能为负数")

    args.model = args.model or default_model()
    print(f"[{args.stage}] {args.mode} · {args.runs} 次 · {args.model} …", file=sys.stderr)
    ev = evaluate(args.stage, args.files, args.context, args.transcript, args.runs, args.model, args.effort,
                  args.frames, args.platform_hint, args.rubric, mode=args.mode)
    result, tech, runs, usage = ev["result"], ev["tech"], ev["raw_runs"], ev["usage"]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.stage}_{Path(args.files[0]).stem}_{datetime.now():%Y%m%d_%H%M%S}"
    (out / f"{stem}.json").write_text(json.dumps({"result": result, "tech": tech, "raw_runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{stem}.md").write_text(render_markdown(result, tech, args, usage), encoding="utf-8")
    print(f"结论：{result['verdict']} · 总分 {result['total']} · 报告：{out / stem}.md")


if __name__ == "__main__":
    main()
