"""P-1 离线分析（0 调用）：只读已有结果，写 results/offline/<name>/metrics.json 与 report.md。

python tests/bench/offline.py                                   # 默认分析 results/b1/r1（+ r2 做稳定性对照）
python tests/bench/offline.py --results results/v2/r1 --name v2 # 第二轮结果出来后同样能跑 b19 / e5

b19 输出契约与自洽（每一次采样）、b23 采样次数模拟（runs=1/2 vs 3）、b16 红线聚合规则与人审分流 / 决策代价、
e5 变体新增问题是否落在注入维度。代价表和分流规则网格是我定的，没有业务方确认。
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

from common import RESULTS, RUBRIC, dim_ids, load_all, rate, redline_ids
from score import load_results, metrics as score_metrics, parse_hit, parse_score, view
from score_v2 import TIER, times_in

NEG = re.compile(r"不构成|无明显|未涉及|未发现|没有发现|不存在|未见|无相关")


# ---------------- b19 ----------------

def b19(res, labels):
    flags = {k: [] for k in ("schema_ok", "top_fixes_3", "score_issue_consistent", "hit_evidence_consistent")}
    tc_n = tc_oob = 0
    examples = {k: [] for k in flags}
    for cid, r in res.items():
        lab = labels.get(cid)
        if not lab:
            continue
        ids, rids = set(dim_ids(lab["stage"])), set(redline_ids(lab["stage"]))
        dur = (r.get("tech") or {}).get("时长(秒)")
        for i, run in enumerate(r["raw_runs"]):
            dims = [d for d in run.get("dimensions") or [] if isinstance(d, dict)]
            rls = [x for x in run.get("redlines") or [] if isinstance(x, dict)]
            ok = ({d.get("id") for d in dims} == ids and len(dims) == len(ids) and {x.get("id") for x in rls} >= rids
                  and all(parse_score(d.get("score")) is not None for d in dims) and all(parse_hit(x.get("hit")) is not None for x in rls))
            tf3 = isinstance(run.get("top_fixes"), list) and len(run["top_fixes"]) == 3
            # 5 分不该列问题，≤2 分必须列问题
            sic = all(not (parse_score(d.get("score")) == 5 and d.get("issues")) and
                      not ((parse_score(d.get("score")) or 3) <= 2 and not d.get("issues")) for d in dims)
            hec = all(not (parse_hit(x.get("hit")) and NEG.search(str(x.get("evidence", ""))[:40])) for x in rls)
            for k, v in (("schema_ok", ok), ("top_fixes_3", tf3), ("score_issue_consistent", sic), ("hit_evidence_consistent", hec)):
                flags[k].append(v)
                if not v and len(examples[k]) < 8:
                    examples[k].append(f"{cid}#{i + 1}")
            if dur:
                for d in dims:
                    ts = times_in(str(d.get("evidence", "")))
                    tc_n += len(ts)
                    tc_oob += sum(1 for t in ts if t > dur + 0.5)
    M = {f"b19.{k}": {**rate(v), "examples": examples[k]} for k, v in flags.items()}
    M["b19.timecode_oob"] = {"value": round(tc_oob / tc_n, 4) if tc_n else None, "n": tc_n, "oob": tc_oob}
    M["b19.hit_evidence_consistent"]["note"] = "关键词初筛（evidence 开头出现否定词）；候选需人工或 Claude 复核"
    return M


# ---------------- b23 ----------------
B23_KEYS = ("b1.recall", "b2.fpr_noredline", "b3.sensitivity", "b4.invariance")


def b23(res, labels):
    full = {c: view(labels[c], r) for c, r in res.items() if c in labels}
    M = {}
    for k in (1, 2):
        sub = {c: view(labels[c], r, k) for c, r in res.items() if c in labels}
        agree = [sub[c]["verdict"] == full[c]["verdict"] for c in sub]
        M[f"b23.runs{k}.verdict_agree"] = rate(agree)
        m, _, _ = score_metrics(res, labels, k)
        for key in B23_KEYS:
            if key in m:
                M[f"b23.runs{k}.{key}"] = m[key]
    m, _, _ = score_metrics(res, labels, None)
    for key in B23_KEYS:
        if key in m:
            M[f"b23.runs3.{key}"] = m[key]
    return M


# ---------------- b16 ----------------
COST = {"miss_redline": 10, "quality_pass": 3, "false_reject": 2, "adjacent": 1, "review": 0.5}


def expected(lab):
    k = lab["kind"]
    if k == "redline" or lab["expect"].get("redlines"):
        return "reject"
    if k == "quality":
        return "not_pass"
    if k in ("base", "invariance"):
        return "not_reject"
    return None


def b16(res, labels):
    rows = []
    for cid, r in res.items():
        lab = labels.get(cid)
        if not lab or lab.get("split") != "test" or not expected(lab):
            continue
        v = view(lab, r)
        singles = [view(lab, {"raw_runs": [run]}) for run in r["raw_runs"]]
        rows.append({"cid": cid, "exp": expected(lab), "v": v, "tier": TIER.get(v["verdict"]),
                     "run_disagree": len({s["verdict"] for s in singles}) > 1,
                     "spread2": any((d["spread"] or 0) >= 2 for d in v["dims"].values()),
                     "suspect": bool(v["suspect_set"]), "missing": bool(v["missing_dims"]), "red": set(lab["expect"].get("redlines") or [])})
    M = {}
    # 红线聚合规则：任一 / 过半 / 全中（只看注入了红线的用例与无红线用例）
    for rule, f in (("any", lambda h: h["n_hit"] > 0), ("majority", lambda h: h["n_hit"] * 2 > h["n"]), ("all", lambda h: h["n_hit"] == h["n"])):
        rec = [all(f(x["v"]["hits"][rid]) for rid in x["red"]) for x in rows if x["red"]]
        fp = [any(f(h) for h in x["v"]["hits"].values()) for x in rows if not x["red"] and labels[x["cid"]]["expect"].get("no_redline")]
        M[f"b16.redline_rule/{rule}"] = {"recall": rate(rec), "fpr": rate(fp)}

    def cost(x, reviewed):
        if reviewed:
            return COST["review"]
        t = x["tier"]
        if x["exp"] == "reject" and t != "reject":
            return COST["miss_redline"]
        if x["exp"] == "not_pass" and t == "pass":
            return COST["quality_pass"]
        if x["exp"] == "not_reject" and t == "reject":
            return COST["false_reject"]
        return 0

    # 产品现行规则 = 维度极差 ≥2 或疑似红线；其余是候选规则（及格线 / 通过线 ± w、单次采样判定不一致）
    band = lambda x, w: x["suspect"] or any(abs((x["v"]["total"] or 0) - t) <= w for t in (3.0, 4.0))
    policies = {"product": lambda x: x["spread2"] or x["suspect"],
                "disagree": lambda x: x["run_disagree"] or x["suspect"],
                "product+disagree": lambda x: x["spread2"] or x["suspect"] or x["run_disagree"]}
    for w in (0.1, 0.2, 0.3, 0.5):
        policies[f"band{w}"] = lambda x, w=w: band(x, w)
        policies[f"band{w}+disagree"] = lambda x, w=w: band(x, w) or x["run_disagree"]
    grid = {}
    for name, p in policies.items():
        rev = [bool(p(x)) for x in rows]
        miss = [x["exp"] == "reject" and x["tier"] != "reject" and not r for x, r in zip(rows, rev) if x["exp"] == "reject"]
        grid[name] = {"review_rate": round(sum(rev) / len(rows), 3), "miss_rate": round(sum(miss) / len(miss), 3) if miss else None,
                      "cost_per_case": round(sum(cost(x, r) for x, r in zip(rows, rev)) / len(rows), 3)}
    best = min(grid, key=lambda k: grid[k]["cost_per_case"])
    M["b16.policy_grid"] = grid
    M["b16.best_policy"] = {"value": best, **grid[best]}
    M["b16.unstable_caught_by_product"] = rate([x["spread2"] or x["suspect"] for x in rows if x["run_disagree"]])
    M["b16.n"] = {"n": len(rows)}
    return M


# ---------------- e5 ----------------

def issue_up(r, base):
    """r 比 base 每次采样平均多出 ≥1 条问题的维度 → 多出的条数（采样间问题条数本身有波动，少于 1 条不算）。"""
    cnt = lambda rr: Counter(d.get("id") for run in rr["raw_runs"] for d in run.get("dimensions") or []
                             if isinstance(d, dict) for _ in (d.get("issues") or []))
    a, b = cnt(r), cnt(base)
    na, nb = len(r["raw_runs"]), len(base["raw_runs"])
    return {d: a[d] / na - b[d] / nb for d in a if a[d] / na - b[d] / nb >= 1 - 1e-9}


def e5(res, labels, noise_res=None):
    """质量缺陷变体比基准多出来的问题，按维度：落在注入维度的比例（其余记"可能编造或光环"）。
    noise_res：同一批基准的另一轮结果，算"什么都没改时也会多出问题的维度数"作为噪声底。"""
    rel, extra_dims = [], Counter()
    five_issue = []
    for cid, r in res.items():
        lab = labels.get(cid)
        if not lab or lab.get("kind") != "quality" or not lab.get("base_case_id") or lab["base_case_id"] not in res:
            continue
        up = issue_up(r, res[lab["base_case_id"]])
        if not up:
            continue
        tgt = set(lab["expect"]["target"])
        rel.append(sum(v for d, v in up.items() if d in tgt) / sum(up.values()))
        extra_dims.update(d for d in up if d not in tgt)
    noise = [len(issue_up(noise_res[c], res[c])) for c in (noise_res or {}) if c in res and labels.get(c, {}).get("kind") == "base"]
    for cid, r in res.items():
        for run in r["raw_runs"][:1]:
            for d in run.get("dimensions") or []:
                if isinstance(d, dict) and parse_score(d.get("score")) == 5 and d.get("issues") and len(five_issue) < 20:
                    five_issue.append({"case": cid, "dim": d.get("id"), "issue": str(d["issues"][0])[:80]})
    return {"e5.new_issue_relevant": {"value": round(statistics.mean(rel), 3) if rel else None, "n": len(rel)},
            "e5.noise_dims_per_base": {"value": round(statistics.mean(noise), 2) if noise else None, "n": len(noise),
                                       "note": "同一基准两轮之间、什么都没改，也多出 ≥1 条问题的维度个数"},
            "e5.extra_issue_dims": dict(extra_dims.most_common(10)), "e5.five_with_issues_sample": five_issue}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(RESULTS / "b1" / "r1"))
    ap.add_argument("--noise", default=str(RESULTS / "b1" / "r2"), help="同一批用例的另一轮结果（e5 噪声底）")
    ap.add_argument("--name", default="b1")
    args = ap.parse_args()
    res = load_results(args.results)
    if not res:
        sys.exit(f"{args.results} 里没有结果")
    labels = {l["case_id"]: l for l in load_all()}
    noise = load_results(args.noise) if Path(args.noise).is_dir() else None
    M = {**b19(res, labels), **e5(res, labels, noise)}
    main_like = {c: r for c, r in res.items() if labels.get(c, {}).get("kind") in ("base", "redline", "quality", "invariance")}
    if main_like:
        M.update(b23(main_like, labels))
        M.update(b16(main_like, labels))
    out = RESULTS / "offline" / args.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(M, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in M.items() if not k.endswith(("sample", "grid"))}, ensure_ascii=False, indent=1, default=str))
    print(f"写入 {out / 'metrics.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
