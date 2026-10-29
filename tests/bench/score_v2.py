"""第二轮（b9–b22、e1–e6）评分：逐条判定标签里的 checks，汇总成指标，写 metrics.json / report.md。

python tests/bench/score_v2.py --results results/v2/r1                      # 比较对象默认还从 results/b1/r1 找
python tests/bench/score_v2.py --results results/v2/r1 --also results/b1/r1 results/b1/r2

聚合口径沿用 score.view（独立聚合，过半采样算命中）。check 的语义见 v2lib.py 顶部。
"""
import argparse
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import MIN_N, RESULTS, V2, cost_cny, gate_state, load_all, load_v2, qwk, rate
from evidence import SHOT_RE
from score import load_results, view

TIER = {"通过": "pass", "修改后通过": "revise", "驳回": "reject", "驳回（命中红线）": "reject"}
TIERS = ["pass", "revise", "reject"]
SHOT2_RE = re.compile(r"第\s*(\d{1,2})\s*(?:镜|个镜头)|(?:Shot|shot|S)\s*(\d{1,2})\b")
# 时间码只认"12.5s / 12 秒"；"9:16"（画幅）、"03:00"（画面里的时钟）这类冒号写法歧义太大，不认。
# 前面是 时长 / 片长 / 要求 等的是在说总时长，不是时间码。
TIME_RE = re.compile(r"(?<![\d.:x])(\d{1,3}(?:\.\d+)?)\s*(?:s|秒)(?![a-zA-Z])")
DURATION_CTX = re.compile(r"(时长|片长|总长|全片|要求|平台|规范|标准|约|共|单镜|每镜|持续|长达|超过)\s*[:：]?\s*$")
FLOOR = 0.5  # 下降类 check：比较对象 ≤ FLOOR + 要求降幅时无法再降，记为不可判定


# ---------------- 取值 ----------------

class Ctx:
    def __init__(self, res, labels):
        self.res, self.labels, self._v = res, labels, {}

    def view(self, cid):
        if cid not in self._v:
            self._v[cid] = view(self.labels[cid], self.res[cid]) if cid in self.res and cid in self.labels else None
        return self._v[cid]

    def x(self, cid, dims):
        """dims="total" 取加权总分，否则取各维度均分的平均；缺任何一个返回 None。"""
        v = self.view(cid)
        if v is None:
            return None
        if dims == "total":
            return v["total"]
        ms = [v["dims"].get(d, {}).get("mean") for d in dims]
        return None if any(m is None for m in ms) else statistics.mean(ms)

    def runs(self, cid):
        return self.res[cid]["raw_runs"] if cid in self.res else []


def text_of(run, where):
    """一次采样里 where 指定位置的文字；"dims:A3|dims:A5" 取几处拼起来。"""
    if "|" in where:
        return "\n".join(text_of(run, w) for w in where.split("|"))
    dims = [d for d in run.get("dimensions") or [] if isinstance(d, dict)]
    rls = [r for r in run.get("redlines") or [] if isinstance(r, dict)]
    j = lambda xs: "\n".join(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in xs)
    if where.startswith("dims:"):
        d = next((d for d in dims if d.get("id") == where[5:]), {})
        return j([d.get("evidence", "")] + list(d.get("issues") or []) + list(d.get("suggestions") or []))
    if where.startswith("redlines:"):
        return j([r.get("evidence", "") for r in rls if r.get("id") == where[9:]])
    if where == "top_fixes":
        return j(run.get("top_fixes") or [])
    if where == "top1":
        return j((run.get("top_fixes") or [""])[:1])
    if where == "issues":
        return j([i for d in dims for i in (d.get("issues") or [])])
    return json.dumps(run, ensure_ascii=False)


def times_in(text):
    return [float(m.group(1)) for m in TIME_RE.finditer(text) if not DURATION_CTX.search(text[max(0, m.start() - 6):m.start()])]


def located(text, loc, stem_alias=r"主视觉|KV"):
    if "shot" in loc:
        shots = {int(s) for s in SHOT_RE.findall(text)} | {int(a or b) for a, b in SHOT2_RE.findall(text)}
        return loc["shot"] in shots
    if "t" in loc:
        a, z = loc["t"]
        return any(a - 1 <= t <= z + 1 for t in times_in(text))
    if "image" in loc:
        stem = loc["image"].rsplit(".", 1)[0]
        bare = re.sub(r"^\d+_", "", stem)
        return stem in text or bare in text or bool(re.search(stem_alias, text)) and "主视觉" in stem
    if "quote" in loc:
        return re.sub(r"\s", "", loc["quote"]) in re.sub(r"\s", "", text)
    raise ValueError(loc)


def is_hit(run, rid):
    from score import parse_hit
    return any(parse_hit(r.get("hit")) for r in run.get("redlines") or [] if isinstance(r, dict) and r.get("id") == rid)


# ---------------- 逐条判定 ----------------

def judge(c, cid, ctx):
    """返回 (ok, value)：ok 为 None 表示不可判定（缺结果、缺维度、比较对象已触底）。"""
    t = c["t"]
    if t == "redline":
        v = ctx.view(cid)
        if v is None:
            return None, None
        if c.get("clean"):
            base = ctx.view(c["clean"])
            if base is None or set(c["ids"]) & base["hits_set"]:
                return None, None  # 基准缺结果或本来就命中：分不清是不是注入导致的
        return all((r in v["hits_set"]) == c["hit"] for r in c["ids"]), None
    if t == "delta":
        a, b = c.get("a") or cid, c.get("b") or cid
        xa, xb = ctx.x(a, c["dims"]), ctx.x(b, c["dims"])
        if xa is None or xb is None:
            return None, None
        d = xa - xb
        lo, hi = c.get("lo"), c.get("hi")
        # 下降类（要求降 ≥ 0.5）：比较对象 a 已接近下限、降不了那么多，不计入（与第一轮 b3 "基准 ≤1.5 排除"同口径）
        if lo is not None and lo >= 0.5 and xa <= FLOOR + lo + 1e-9:
            return None, d
        # 下降类：降幅不够但已经降到 ≤1.5（"差"这一档）也算发现了（与第一轮 b3 同口径）
        if lo is not None and lo >= 0.5 and hi is None and d > 0 and xb <= 1.5 + 1e-9:
            return True, round(d, 3)
        return (lo is None or d >= lo - 1e-9) and (hi is None or d <= hi + 1e-9), round(d, 3)
    if t == "verdict":
        v = ctx.view(cid)
        if v is None:
            return None, None
        return (not c.get("allow") or v["verdict"] in c["allow"]) and v["verdict"] not in (c.get("deny") or []), None
    if t == "mention":
        runs = ctx.runs(cid)
        if not runs:
            return None, None
        if c.get("clean"):
            base = ctx.runs(c["clean"])
            if not base or sum(1 for r in base if re.search(c["pattern"], text_of(r, c["where"]))) * 2 > len(base):
                return None, None
        k = sum(1 for r in runs if re.search(c["pattern"], text_of(r, c["where"])))
        return k * 2 > len(runs), k / len(runs)
    if t == "locus":
        runs = ctx.runs(cid)
        if c["where"].startswith("redlines:"):
            runs = [r for r in runs if is_hit(r, c["where"][9:])]
        if not runs:
            return None, None
        k = sum(1 for r in runs if located(text_of(r, c["where"]), c["loc"]))
        return k * 2 > len(runs), k / len(runs)
    if t == "order":
        xs = [ctx.x(i, c["dims"]) for i in c["ids"]]
        if any(x is None for x in xs):
            return None, None
        ok = all(b <= a + c["tol"] + 1e-9 for a, b in zip(xs, xs[1:])) and xs[0] > xs[-1] + 1e-9
        return ok, [round(x, 2) for x in xs]
    raise ValueError(f"未知 check 类型 {t}")


# ---------------- 汇总 ----------------

def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def srcc_ci(xs, ys, iters=2000, seed=0):
    rnd = random.Random(seed)
    n, out = len(xs), []
    for _ in range(iters):
        idx = [rnd.randrange(n) for _ in range(n)]
        s = spearman([xs[i] for i in idx], [ys[i] for i in idx])
        if s is not None:
            out.append(s)
    out.sort()
    return (round(out[int(len(out) * 0.025)], 3), round(out[int(len(out) * 0.975) - 1], 3)) if out else (None, None)


def metrics(res, v2_labels, meta, all_labels):
    ctx = Ctx(res, all_labels)
    flags, deltas, report_only, corr_pts = defaultdict(list), defaultdict(list), defaultdict(lambda: True), defaultdict(list)
    fails, undecided, missing = [], Counter(), [l["case_id"] for l in v2_labels if l["case_id"] not in res]
    for l in v2_labels:
        cid = l["case_id"]
        for c in l["checks"]:
            k = c["key"]
            report_only[k] &= bool(c.get("report"))
            if c["t"] == "corr":
                x = ctx.x(cid, c["dims"])
                if x is None:
                    undecided[k] += cid in res
                else:
                    corr_pts[k].append((x, c["truth"], cid))
                continue
            if cid not in res:
                continue
            ok, val = judge(c, cid, ctx)
            if ok is None:
                undecided[k] += 1
                continue
            flags[k].append(ok)
            if c["t"] == "delta" and val is not None:
                deltas[k].append(val)
            if not ok and not c.get("report"):
                fails.append((cid, k, val))
    M = {}
    for k, fs in flags.items():
        M[k] = rate(fs)
        if deltas[k]:
            M[k]["mean_delta"] = round(statistics.mean(deltas[k]), 3)
    # "x/y" 分组的合并值 "x"（分组样本少时门槛设在合并值上）；只报告与否跟分组一致
    for parent in {k.split("/")[0] for k in flags if "/" in k} - set(flags):
        subs = [k for k in flags if k.startswith(parent + "/")]
        M[parent] = rate([f for k in subs for f in flags[k]])
        report_only[parent] = all(report_only[k] for k in subs)
        flags[parent] = []
    for k, pts in corr_pts.items():
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        s = spearman(xs, ys)
        lo, hi = srcc_ci(xs, ys) if s is not None else (None, None)
        M[k] = {"value": round(s, 3) if s is not None else None, "n": len(pts), "lo": lo, "hi": hi}
        srt = sorted(pts, key=lambda p: p[1])
        third = len(srt) // 3
        if third:
            gap = statistics.mean(p[0] for p in srt[-third:]) - statistics.mean(p[0] for p in srt[:third])
            M[k.replace("srcc", "group_gap")] = {"value": round(gap, 3), "n": third}
    derived(M, ctx, meta, res)
    M["_report_only"] = sorted(k for k in list(flags) + list(corr_pts) if report_only[k])
    M["_merged"] = sorted(k for k, v in flags.items() if v == [])
    M["_undecided"] = dict(undecided)
    M["data.v2_missing"] = {"n": len(missing), "cases": missing[:30],
                            "by_family": dict(Counter(l["family"] for l in v2_labels if l["case_id"] in set(missing)))}
    got = [r for c, r in res.items() if c in {l["case_id"] for l in v2_labels}]
    M["cost.v2"] = {"cases": len(got), "prompt_tokens": sum(r["usage"].get("prompt_tokens", 0) for r in got),
                    "completion_tokens": sum(r["usage"].get("completion_tokens", 0) for r in got),
                    "estimated_cny": round(sum(cost_cny(r["usage"]) for r in got), 2)}
    return M, fails, ctx


def derived(M, ctx, meta, res):
    """跨用例的指标：梯度单调、规模降幅、位置差、多缺陷召回降幅、最小可识别字号、三档结论。"""
    # b12 梯度单调：相邻点不升（容差 0.25）且首 > 尾
    det = {}
    for name, s in (meta.get("b12") or {}).get("series", {}).items():
        xs = [ctx.x(i, s["dims"]) for i in s["ids"]]
        if any(x is None for x in xs):
            continue
        det[name] = {"levels": [round(x, 2) for x in xs], "ids": s["ids"],
                     "ok": all(b <= a + 0.25 + 1e-9 for a, b in zip(xs, xs[1:])) and xs[0] > xs[-1] + 1e-9}
    if det:
        M["b12.monotone"] = rate([d["ok"] for d in det.values()])
        M["b12.series"] = det
    # 召回随条件的最大降幅：b21 规模（最小 vs 最大）、b18 位置（三个位置的极差）
    def recall(prefix):
        return {k[len(prefix):]: v["rate"] for k, v in M.items() if k.startswith(prefix) and isinstance(v, dict) and v.get("rate") is not None}
    for grp, small, big in (("images", "4", "28"), ("text", "5k", "60k"), ("length", "15s", "180s")):
        r = recall(f"b21.recall/{grp}.")
        if small in r and big in r:
            M[f"b21.scale_drop/{grp}"] = {"value": round(r[small] - r[big], 3)}
    for st in ("storyboard", "asset", "video"):
        r = recall(f"b18.recall/{st}.")
        if len(r) == 3:
            M[f"b18.position_gap/{st}"] = {"value": round(max(r.values()) - min(r.values()), 3)}
    # b21 成本曲线：材料规模 → 每例 token、耗时
    curve = {}
    for name, s in (meta.get("b21") or {}).get("series", {}).items():
        grp = name.rsplit("_", 1)[-1]
        for sc, cid in zip(s["scale"], s["ids"]):
            if cid in res:
                u = res[cid]["usage"]
                curve.setdefault(grp, {}).setdefault(str(sc), []).append((u.get("prompt_tokens", 0) + u.get("completion_tokens", 0),
                                                                          res[cid].get("seconds")))
    if curve:
        M["b21.cost_curve"] = {g: {sc: {"tokens": round(statistics.mean(t for t, _ in v)),
                                        "seconds": round(statistics.mean(s for _, s in v if s), 1) if any(s for _, s in v) else None,
                                        "n": len(v)} for sc, v in d.items()} for g, d in curve.items()}
    # e4 多缺陷召回相对单独注入的降幅
    if "e4.single_recall" in M and "e4.multi_recall" in M and M["e4.multi_recall"]["rate"] is not None:
        M["e4.multi_recall_drop"] = {"value": round(M["e4.single_recall"]["rate"] - M["e4.multi_recall"]["rate"], 3)}
    # b9 可靠识别（R2 召回 ≥ 80%）的最小字号
    fonts = {int(k.rsplit("px", 1)[-1]): v["rate"] for k, v in M.items() if k.startswith("b9.font_px") and v.get("rate") is not None}
    if fonts:
        ok = [px for px, r in sorted(fonts.items()) if all(fonts[q] >= 0.8 for q in fonts if q >= px)]
        M["b9.font_min_px"] = {"value": ok[0] if ok else None, "curve": fonts}
    # e6 三档结论：混淆矩阵、二次加权 κ（3 档）、跨档错（通过 ↔ 驳回）
    tiers = {}
    for m in meta.values():
        tiers.update(m.get("tiers", {}))
    pairs = [(t, TIER.get(ctx.view(c)["verdict"])) for c, t in tiers.items() if ctx.view(c)]
    if pairs:
        cm = {a: {b: sum(1 for x, y in pairs if x == a and y == b) for b in TIERS} for a in TIERS}
        idx = {t: i + 1 for i, t in enumerate(TIERS)}
        M["e6.confusion"] = cm
        M["e6.kappa"] = {"value": round(qwk([idx[a] for a, _ in pairs], [idx[b] for _, b in pairs], k=3), 3), "n": len(pairs)}
        M["e6.cross_tier_errors"] = {"value": sum(1 for a, b in pairs if {a, b} == {"pass", "reject"}), "n": len(pairs)}
        M["e6.accuracy"] = rate([a == b for a, b in pairs])


# ---------------- 门槛与报告 ----------------

def thresholds():
    from common import BENCH
    th = json.loads((BENCH / "thresholds.json").read_text(encoding="utf-8"))
    return {k: v if isinstance(v, list) else [v] for k, v in th.items() if not k.startswith("_")}


def gate(M, key, ts):
    """返回 [(门槛文字, 状态)]，状态见 common.gate_state；与 test_bench_gates 同语义（只支持 rate / value / mean / n）。"""
    out = []
    for t in ts:
        txt = " ".join(x for x in (f"≥ {t['min']}" if "min" in t else "", f"≤ {t['max']}" if "max" in t else "") if x)
        out.append((f"{t['field']} {txt}", gate_state(M[key], t)[0]))
    return out


STATE = {None: "—", "pass": "通过", "fail": "**未通过**", "unsure": "不确定（区间跨过门槛）", "small": f"样本 < {MIN_N}，只报告"}


def fmt(m):
    if not isinstance(m, dict):
        return str(m)
    if "rate" in m:
        if m["rate"] is None:
            return "—"
        s = f"{m['rate']:.1%}（{m['k']}/{m['n']}，95% CI {m['lo']:.0%}–{m['hi']:.0%}）"
        return s + (f"，平均 Δ {m['mean_delta']:+.2f}" if "mean_delta" in m else "")
    if "value" in m:
        ci = f"（95% CI {m['lo']}–{m['hi']}）" if m.get("lo") is not None else ""
        return f"{m['value']}{ci}" + (f"，n={m['n']}" if "n" in m else "")
    return "—"


SKIP = {"b12.series", "b21.cost_curve", "e6.confusion", "data.v2_missing", "cost.v2", "_report_only", "_undecided", "_merged", "_meta"}


def report(M, fails, name, labels):
    th = thresholds()
    fam_n = Counter(l["family"] for l in labels)
    c = M["cost.v2"]
    L = [f"# B 层第二轮评测报告 · {name}", "",
         f"- 用例 {sum(fam_n.values())} 个（{'，'.join(f'{f} {n}' for f, n in sorted(fam_n.items()))}），已有结果 {c['cases']} 个，"
         f"缺 {M['data.v2_missing']['n']} 个",
         f"- token 输入 {c['prompt_tokens']:,} / 输出 {c['completion_tokens']:,}，估算 ¥{c['estimated_cny']}",
         "- 标签来源：构造（注入方式决定）、程序测量、公开数据集人工评分（e1）。范例与 e6 档位由 Claude 撰写 / 判断（非人工）。", "",
         "## 指标", "", "| 指标 | 值 | 门槛 | 结果 |", "|---|---|---|---|"]
    keys = sorted((k for k in M if k not in SKIP and not k.startswith("_")), key=lambda k: (k.split(".")[0], k))
    for k in keys:
        ts = th.get(k) or next((v for p, v in th.items() if p.endswith("/*") and k.startswith(p[:-1])), None)
        if k in M["_report_only"]:
            L.append(f"| `{k}` | {fmt(M[k])} | 只报告 | |")
        elif ts:
            g = gate(M, k, ts)
            L.append(f"| `{k}` | {fmt(M[k])} | {'；'.join(t for t, _ in g)} | {'；'.join(STATE[st] for _, st in g)} |")
        else:
            L.append(f"| `{k}` | {fmt(M[k])} | 无 | |")
    if M.get("b12.series"):
        L += ["", "## 维度梯度（b12）", "", "| 序列 | 各点（范例→基准→轻→中→重） | 单调 |", "|---|---|---|"]
        L += [f"| {k} | {v['levels']} | {'是' if v['ok'] else '**否**'} |" for k, v in sorted(M["b12.series"].items())]
    if M.get("e6.confusion"):
        L += ["", "## 三档结论（e6，行 = 应有档位，列 = 实际结论）", "", "| | 通过 | 修改后通过 | 驳回 |", "|---|---|---|---|"]
        L += [f"| {a} | " + " | ".join(str(M["e6.confusion"][a][b]) for b in TIERS) + " |" for a in TIERS]
    if M.get("b21.cost_curve"):
        L += ["", "## 规模 → 成本（b21，每例 3 次采样合计）", "", "| 组 | 规模 | token | 秒 | n |", "|---|---|---|---|---|"]
        L += [f"| {g} | {sc} | {v['tokens']:,} | {v['seconds']} | {v['n']} |" for g, d in M["b21.cost_curve"].items() for sc, v in d.items()]
    if M["_undecided"]:
        L += ["", "## 不可判定（缺维度、比较对象缺结果、比较对象已触底）", ""]
        L += [f"- `{k}`：{n}" for k, n in sorted(M["_undecided"].items()) if n]
    L += ["", "判定口径：比率 n < 10 只报告；点估计没达标但 95% 区间跨过门槛记「不确定」，区间整体越过门槛才算未通过。"
              "x/y 分组的合并值记为 x，门槛优先设在合并值上。"]
    L += ["", "## 未通过的 check（不含只报告项）", ""]
    L += [f"- `{c}` {k}：{v}" for c, k, v in fails[:80]] or ["无"]
    if len(fails) > 80:
        L.append(f"- ……共 {len(fails)} 条，见 metrics.json")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(RESULTS / "v2" / "r1"))
    ap.add_argument("--also", nargs="*", default=[str(RESULTS / "b1" / "r1")], help="比较对象所在的已有结果目录")
    ap.add_argument("--name", default="v2")
    args = ap.parse_args()
    res = {}
    for d in args.also + [args.results]:  # 本轮结果优先
        if Path(d).is_dir():
            res.update(load_results(d))
    v2 = load_v2()
    if not v2:
        sys.exit("没有第二轮标签：先运行 cases_v2.py")
    meta_p = V2 / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    labels = {l["case_id"]: l for l in load_all()}
    M, fails, _ = metrics(res, v2, meta, labels)
    M["_meta"] = {"name": args.name, "results": args.results, "also": args.also, "fails": len(fails)}
    out = Path(args.results)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(M, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "fails.json").write_text(json.dumps(fails, ensure_ascii=False, indent=1), encoding="utf-8")
    rep = report(M, fails, args.name, v2)
    (out / "report.md").write_text(rep, encoding="utf-8")
    print(rep)


if __name__ == "__main__":
    main()
