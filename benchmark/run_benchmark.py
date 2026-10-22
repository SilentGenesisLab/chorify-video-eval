#!/usr/bin/env python3
"""在基准数据集上运行评审器并计算指标。

python run_benchmark.py --name run1                 # 全量，每例采样 1 次
python run_benchmark.py --name stab --runs 3 --variants base inv_fluff   # 稳定性子集
python run_benchmark.py --name run1 --score-only    # 只重算指标
结果缓存在 results/<name>/，中断后重跑会跳过已完成的用例。
"""
import argparse
import csv
import json
import statistics
import sys
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import video_review  # noqa: E402

STAGES = ["creative", "storyboard", "asset", "video"]


def load_labels(args):
    rows = [json.loads(x) for x in (HERE / "dataset" / "labels.jsonl").read_text().splitlines() if x.strip()]
    if args.stages:
        rows = [r for r in rows if r["stage"] in args.stages]
    if args.scenarios:
        rows = [r for r in rows if r["scenario"] in args.scenarios]
    if args.variants:
        rows = [r for r in rows if r["variant"] in args.variants]
    if args.split:
        rows = [r for r in rows if r["split"] == args.split]
    return rows


def run_case(lab, args, key):
    inp = lab["inputs"]
    p = lambda x: str(HERE / x)
    t0 = time.time()
    ev = video_review.evaluate(lab["stage"], [p(f) for f in inp["files"]], [p(c) for c in inp.get("context", [])],
                               p(inp["transcript"]) if inp.get("transcript") else None, args.runs, args.model,
                               args.effort, platform_hint=inp.get("platform_hint", video_review.DEFAULT_PLATFORM_HINT), key=key)
    ev["seconds"] = round(time.time() - t0, 1)
    ev["case_id"] = lab["case_id"]
    return ev


def run_all(labels, args):
    out = HERE / "results" / args.name
    out.mkdir(parents=True, exist_ok=True)
    todo = [l for l in labels if not (out / f"{l['case_id']}.json").exists()]
    print(f"共 {len(labels)} 例，待运行 {len(todo)} 例，并发 {args.workers}", file=sys.stderr)
    key = video_review.load_api_key()
    done = 0
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(run_case, l, args, key): l for l in todo}
        for f in as_completed(futs):
            lab = futs[f]
            done += 1
            try:
                ev = f.result()
                (out / f"{lab['case_id']}.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1))
                r = ev["result"]
                print(f"[{done}/{len(todo)}] {lab['case_id']}: {r['verdict']} {r['total']} ({ev['seconds']}s)", file=sys.stderr)
            except Exception as e:
                print(f"[{done}/{len(todo)}] {lab['case_id']} 失败：{e}", file=sys.stderr)
                traceback.print_exc()


# ---------------- 指标 ----------------

def pct(a, b):
    return f"{a / b * 100:.0f}% ({a}/{b})" if b else "—"


def score(labels, args):
    out = HERE / "results" / args.name
    res = {}
    for l in labels:
        f = out / f"{l['case_id']}.json"
        if f.exists():
            res[l["case_id"]] = json.loads(f.read_text())
    labs = {l["case_id"]: l for l in labels if l["case_id"] in res}
    if not labs:
        sys.exit("没有可评分的结果")

    def view(cid):
        r = res[cid]["result"]
        return {"total": r["total"], "verdict": r["verdict"],
                "dims": {d["id"]: d["mean"] for d in r["dimensions"]},
                "hits": {x["id"] for x in r["redlines"] if x["status"] == "命中"},
                "suspect": {x["id"] for x in r["redlines"] if x["status"].startswith("疑似")},
                "spreads": [d["spread"] for d in r["dimensions"] if d["spread"] is not None]}

    V = {cid: view(cid) for cid in labs}
    rows, fails = [], []
    agg = defaultdict(lambda: defaultdict(list))  # stage -> metric -> [bool/number]
    per_variant = defaultdict(lambda: defaultdict(list))

    for cid, l in sorted(labs.items()):
        v, st, kind, exp = V[cid], l["stage"], l["kind"], l["expect"]
        base = V.get(l["base_case_id"]) if l["base_case_id"] else None
        row = {"case_id": cid, "stage": st, "variant": l["variant"], "kind": kind, "total": v["total"], "verdict": v["verdict"],
               "hits": ",".join(sorted(v["hits"])), "expected_redlines": ",".join(exp["redlines"]),
               "target": ",".join(exp["target"]), "delta_target": "", "delta_total": "", "pass": ""}
        ok = True
        if kind == "redline":
            rec = set(exp["redlines"]) <= v["hits"]
            agg[st]["红线召回（命中指定红线）"].append(rec)
            agg[st]["红线检出（命中任一红线）"].append(bool(v["hits"]))
            agg[st]["红线用例判驳回"].append(v["verdict"].startswith("驳回"))
            per_variant[(st, l["variant"])]["pass"].append(rec)
            ok = rec
            if not rec:
                fails.append((cid, f"应命中 {exp['redlines']}，实际命中 {sorted(v['hits']) or '无'}，疑似 {sorted(v['suspect']) or '无'}"))
        if exp["no_redline"]:
            fa = bool(v["hits"])
            agg[st][f"误报率（{ {'base': '基准', 'quality': '质量变体', 'invariance': '不变性变体'}[kind]}）"].append(fa)
            agg[st]["误报率（全部无红线用例）"].append(fa)
            if fa:
                ok = False
                fails.append((cid, f"不应命中红线，实际命中 {sorted(v['hits'])}"))
        if kind == "base":
            agg[st]["基准总分"].append(v["total"])
            agg[st]["基准判定为通过/修改后通过"].append(not v["verdict"].startswith("驳回"))
        if base and exp["target"]:
            t0 = exp["target"][0]
            bt, vt = base["dims"].get(t0), v["dims"].get(t0)
            if bt is not None and vt is not None:
                d = round(vt - bt, 2)
                row["delta_target"] = d
                if bt <= 1.5:
                    agg[st]["目标维度触底（无法再降，已排除）"].append(1)
                else:
                    hit = d <= -1 or any((v["dims"].get(t, 9) - base["dims"].get(t, 0)) <= -1 for t in exp["target"][1:])
                    agg[st]["缺陷灵敏度（目标维度降 ≥1 分）"].append(hit)
                    agg[st]["目标维度平均变化"].append(d)
                    per_variant[(st, l["variant"])]["pass"].append(hit)
                    if kind == "quality":
                        ok = ok and hit
                    if not hit:
                        fails.append((cid, f"目标维度 {t0}：基准 {bt} → 变体 {vt}（Δ{d}）"))
                others = [abs(v["dims"][k] - base["dims"][k]) for k in v["dims"] if k not in exp["target"] and v["dims"][k] is not None and base["dims"].get(k) is not None]
                if others:
                    agg[st]["非目标维度平均 |Δ|（越小越专一）"].append(statistics.mean(others))
        if base and kind == "quality":
            agg[st]["质量变体总分低于基准"].append(v["total"] < base["total"])
        if base:
            row["delta_total"] = round(v["total"] - base["total"], 2)
        if kind == "invariance" and base:
            inv = abs(v["total"] - base["total"]) <= 0.3
            agg[st]["不变性（|Δ总分| ≤ 0.3）"].append(inv)
            agg[st]["不变性变体 Δ总分"].append(v["total"] - base["total"])
            per_variant[(st, l["variant"])]["pass"].append(inv)
            ok = ok and inv
            if not inv:
                fails.append((cid, f"内容未变，总分 {base['total']} → {v['total']}"))
        if v["spreads"] and len(res[cid]["raw_runs"]) > 1:
            agg[st]["多次采样分歧 ≥2 的维度占比"].extend(s >= 2 for s in v["spreads"])
            agg[st]["多次采样平均极差"].extend(v["spreads"])
        row["pass"] = ok
        rows.append(row)

    # 汇总表
    metric_names = []
    for st in STAGES:
        for m in agg[st]:
            if m not in metric_names:
                metric_names.append(m)

    def fmt(vals, m):
        if not vals:
            return "—"
        if m.startswith("目标维度触底"):
            return str(len(vals))
        if isinstance(vals[0], bool):
            return pct(sum(vals), len(vals))
        return f"{statistics.mean(vals):+.2f}" if "Δ" in m or "变化" in m else f"{statistics.mean(vals):.2f}"

    stages = [s for s in STAGES if agg[s]]
    usage = defaultdict(int)
    secs = []
    for e in res.values():
        for k, n in e["usage"].items():
            usage[k] += n
        secs.append(e["seconds"])

    L = [f"# 评审器基准测试报告 · {args.name}", "",
         f"- 模型：{args.model} · 每例采样 {args.runs} 次 · 已评测用例 {len(labs)}",
         f"- Token：输入 {usage['prompt_tokens']:,} / 输出 {usage['completion_tokens']:,} · 单例平均耗时 {statistics.mean(secs):.0f}s",
         f"- 用例整体通过率：{pct(sum(r['pass'] for r in rows), len(rows))}", "",
         "## 分关卡指标", "", "| 指标 | " + " | ".join(stages) + " |", "|---|" + "---|" * len(stages)]
    for m in metric_names:
        L.append(f"| {m} | " + " | ".join(fmt(agg[s].get(m, []), m) for s in stages) + " |")
    L += ["", "## 分变体通过率", "", "| 关卡 | 变体 | 说明 | 通过率 |", "|---|---|---|---|"]
    desc = {(l["stage"], l["variant"]): l["description"] for l in labs.values()}
    for (st, var), d in sorted(per_variant.items(), key=lambda x: (STAGES.index(x[0][0]), x[0][1])):
        L.append(f"| {st} | {var} | {desc.get((st, var), '')} | {pct(sum(d['pass']), len(d['pass']))} |")
    L += ["", "## 未通过用例", ""] + [f"- `{c}`：{msg}" for c, msg in fails]
    L += ["", "## 指标说明", "",
          "- **红线召回**：注入了某条红线的用例中，评审器命中该红线的比例。目标 ≥ 90%。",
          "- **误报率**：未注入红线的用例中，评审器判定命中任一红线的比例。目标 ≤ 10%。",
          "- **缺陷灵敏度**：注入质量缺陷后，目标维度相对基准下降 ≥ 1 分的比例（基准该维度 ≤1.5 分时无法再降，排除）。目标 ≥ 80%。",
          "- **非目标维度平均 |Δ|**：注入一个缺陷时其他维度的连带变化，越小说明维度区分度越好。",
          "- **不变性**：只改格式或追加无信息套话，总分变化应 ≤ 0.3。用于检测冗长偏好和格式偏差。",
          "- **多次采样分歧**：同一用例多次评分的极差，用于衡量稳定性（需 --runs ≥ 2）。",
          "- 资产与成片用例为示意图和分镜动态预演，**绝对分数没有参考意义**，只看红线和相对变化。"]
    (out / "report.md").write_text("\n".join(L) + "\n")
    summary = {"name": args.name, "model": args.model, "runs": args.runs, "cases": len(labs),
               "usage": dict(usage), "avg_seconds": round(statistics.mean(secs)),
               "passed": sum(r["pass"] for r in rows), "stages": stages,
               "metrics": [{"name": m, "values": {s: fmt(agg[s].get(m, []), m) for s in stages}} for m in metric_names],
               "variants": [{"stage": st, "variant": var, "description": desc.get((st, var), ""),
                             "passed": sum(d["pass"]), "total": len(d["pass"])}
                            for (st, var), d in sorted(per_variant.items(), key=lambda x: (STAGES.index(x[0][0]), x[0][1]))],
               "failures": [{"case_id": c, "reason": msg} for c, msg in fails], "rows": rows}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    with open(out / "cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n".join(L[:len(L)]))
    print(f"\n报告：{out / 'report.md'}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--stages", nargs="*")
    ap.add_argument("--scenarios", nargs="*")
    ap.add_argument("--variants", nargs="*")
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--score-only", action="store_true")
    args = ap.parse_args()
    labels = load_labels(args)
    if not args.score_only:
        run_all(labels, args)
    score(labels, args)


if __name__ == "__main__":
    main()
