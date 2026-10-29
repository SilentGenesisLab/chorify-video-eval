"""B7 证据可核验：评审 evidence 里用引号引用的原文片段，是否真的出现在材料里。

只核验引号内的片段（「」『』“”""），≥ 4 个字符；中间有省略号的拆开逐段核验。
规范化后做子串匹配：去空白、去 markdown 符号、全角标点转半角、去引号。
来源分三类：material（在材料 / 技术参数 / 平台说明里找到）、rubric（只在评分标准里找到，引用的是标准不是材料）、
unverified（都找不到：可能是转述、改写，也可能是编造）。图片、视频画面里的文字只能部分核验（卡片文字来自分镜上下文）。
另查镜号引用：引用了材料里不存在的镜号（如分镜只有 7 镜却写"镜 9"）。
"""
import json
import re

from common import RUBRIC, resolve

import video_review  # noqa: E402

QUOTE_RE = re.compile(r"「([^「」]{2,200})」|『([^『』]{2,200})』|“([^“”]{2,200})”|\"([^\"]{2,200})\"")
SPLIT_RE = re.compile(r"……|…|\.\.\.|⋯")
# "单镜 24 秒""分镜30s""每镜11–13字"不是镜号：排除前面是 分/单/运/转/景/长/每 的；
# "第6镜22-26秒""第5镜12个月"里镜后的数字是时间/数量：排除后面紧跟时长、区间、量词的；
# "镜5缺失""镜6 若存在"是在指出镜头被删，不算引用了不存在的镜号
SHOT_RE = re.compile(r"(?<![分单运转景长每])镜\s*(\d{1,2})"
                     r"(?![\d.]|\s*(?:秒|s|S|[-–—~～]\s*\d|个|条|张|字|帧|枚)|\s*(?:缺失|若存在|不存在|被删|已删))")
PART_RE = re.compile(r"[/／、＋+→]|->")
TEXT_EXT = {".md", ".txt", ".srt", ".json", ".csv"}
PUNCT = str.maketrans({"，": ",", "：": ":", "；": ";", "（": "(", "）": ")", "！": "!", "？": "?", "。": ".", "－": "-",
                       "–": "-", "—": "-", "～": "~", "％": "%", "＋": "+", "／": "/", "＝": "="})
MIN_LEN = 4


def norm(s):
    s = s.translate(PUNCT).lower()
    return re.sub(r"[\s*|#`>「」『』“”\"']", "", s)


def rubric_text(stage):
    s = RUBRIC["stages"][stage]
    parts = [s["name"], s["input_hint"], *s["redlines"], *RUBRIC["scale"].values()]
    for d in s["dimensions"]:
        parts += [d["name"], d["criteria"], d["anchor_5"], d["anchor_2"]]
    return norm("\n".join(parts))


def material_text(label, result, data=None):
    inp = label["inputs"]
    parts = []
    for rel in inp["files"] + inp.get("context", []) + ([inp["transcript"]] if inp.get("transcript") else []):
        p = resolve(rel, data)
        parts.append(p.name)
        if p.suffix.lower() in TEXT_EXT and p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    parts.append(inp.get("platform_hint", ""))
    if result.get("tech"):
        parts.append(json.dumps(result["tech"], ensure_ascii=False))
    return norm("\n".join(parts))


def shot_count(label, data=None):
    """材料（文件或上下文）里分镜表的镜头数；没有分镜返回 None。"""
    inp = label["inputs"]
    best = None
    for rel in inp["files"] + inp.get("context", []):
        p = resolve(rel, data)
        if p.suffix.lower() == ".md" and p.exists():
            t = p.read_text(encoding="utf-8", errors="replace")
            nums = [int(m) for m in re.findall(r"^\|\s*(\d{1,2})\s*\|", t, re.M)] + \
                   [int(m) for m in re.findall(r"^\*\*镜 (\d{1,2})\*\*", t, re.M)]
            if nums:
                best = max(best or 0, max(nums))
    return best


def quotes(text):
    for m in QUOTE_RE.finditer(text or ""):
        q = next(g for g in m.groups() if g)
        for frag in SPLIT_RE.split(q):
            if len(norm(frag)) >= MIN_LEN:
                yield frag.strip()


def classify(q, mat, rub, prompt):
    """material / composite（用 / 、 ＋ → 拼起来的摘要，每一段都在材料里）/ near（表格单元格压缩等，
    字符二元组覆盖率 ≥ 0.9；composite 每段 ≥ 0.85）/ prompt（引用的是评审指令）/ rubric / unverified。"""
    nq = norm(q)
    if nq in mat:
        return "material"
    parts = [norm(p) for p in PART_RE.split(q) if len(norm(p)) >= 2]
    if len(parts) >= 2 and all(p in mat or bigram_cov(p, mat) >= 0.85 for p in parts):
        return "composite"
    if bigram_cov(nq, mat) >= 0.9:
        return "near"
    if nq in prompt:
        return "prompt"
    return "rubric" if nq in rub else "unverified"


def bigram_cov(q, text):
    grams = {q[i:i + 2] for i in range(len(q) - 1)}
    return sum(g in text for g in grams) / len(grams) if grams else 1.0


def evidence_texts(result):
    for run in result.get("raw_runs", []):
        for d in run.get("dimensions", []) or []:
            yield d.get("id"), d.get("evidence", "")
        for r in run.get("redlines", []) or []:
            yield r.get("id"), r.get("evidence", "")


def verify(label, result, data=None):
    """返回 {"quotes": [(id, 片段, 状态)], "bad_shots": [(id, 镜号)], "shots": 镜头数, "shot_refs": 镜号引用总数}。"""
    mat, rub = material_text(label, result, data), rubric_text(label["stage"])
    prompt = norm(video_review.build_system_prompt(label["stage"], RUBRIC))
    n_shots = shot_count(label, data)
    out, bad, refs = [], [], 0
    for fid, text in evidence_texts(result):
        if not isinstance(text, str):
            continue
        for q in quotes(text):
            out.append((fid, q, classify(q, mat, rub, prompt)))
        if n_shots:
            found = SHOT_RE.findall(text)
            refs += len(found)
            bad += [(fid, int(s)) for s in found if int(s) > n_shots]
    return {"quotes": out, "bad_shots": bad, "shots": n_shots, "shot_refs": refs}
