#!/usr/bin/env python3
"""人工标注：导出待标注表 → 专家填写 → 计算评审器与人工的一致性。

python human_agreement.py export --n 12          # 每个关卡抽 12 例，生成 annotation/待标注_<关卡>.csv
python human_agreement.py agree --run run1       # 读取已填写的 CSV，与 results/run1 对比
"""
import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ANN = HERE / "annotation"
VERDICTS = ["通过", "修改后通过", "驳回"]


def rubric():
    return json.loads((ROOT / "rubrics.json").read_text())


def export(args):
    labels = [json.loads(x) for x in (HERE / "dataset" / "labels.jsonl").read_text().splitlines() if x.strip()]
    rb = rubric()
    rng = random.Random(args.seed)
    ANN.mkdir(exist_ok=True)
    for stage, spec in rb["stages"].items():
        pool = [l for l in labels if l["stage"] == stage and l["split"] == "test"]
        by_kind = defaultdict(list)
        for l in pool:
            by_kind[l["kind"]].append(l)
        picked = []
        # 分层抽样：基准、红线、质量、不变性按比例
        quota = {"base": 3, "redline": args.n // 3, "invariance": 1}
        quota["quality"] = max(args.n - sum(quota.values()), 0)
        for kind, k in quota.items():
            picked += rng.sample(by_kind[kind], min(k, len(by_kind[kind])))
        rng.shuffle(picked)  # 打乱顺序，且不向标注员暴露变体类型
        dims = [f"{d['id']} {d['name']}" for d in spec["dimensions"]]
        reds = "；".join(f"R{i + 1} {r}" for i, r in enumerate(spec["redlines"]))
        path = ANN / f"待标注_{stage}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "材料（相对 benchmark 目录）", "参考材料"] + dims + ["命中红线（填 R 编号，逗号分隔；无则留空）", "结论（通过/修改后通过/驳回）", "备注", "标注人"])
            for l in picked:
                w.writerow([l["case_id"], " ; ".join(l["inputs"]["files"]), " ; ".join(l["inputs"].get("context", []))] + [""] * len(dims) + ["", "", "", ""])
        print(f"{path}（{len(picked)} 例）　红线：{reds}")


def qwk(a, b, k=5):
    """二次加权 Cohen's kappa，评分 1..k。"""
    n = len(a)
    if n == 0:
        return None
    O = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        O[x - 1][y - 1] += 1
    ha = [sum(r) for r in O]
    hb = [sum(O[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            wgt = (i - j) ** 2 / (k - 1) ** 2
            num += wgt * O[i][j]
            den += wgt * ha[i] * hb[j] / n
    return 1 - num / den if den else None


def kappa(a, b):
    """名义变量 Cohen's kappa。"""
    n = len(a)
    if n == 0:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else None


def agree(args):
    rb = rubric()
    res_dir = HERE / "results" / args.run
    L = [f"# 人工 vs 评审器一致性 · {args.run}", "",
         "参考阈值：κ ≥ 0.6 可用，≥ 0.8 强一致；±1 分一致率 ≥ 85%。", ""]
    for stage, spec in rb["stages"].items():
        path = ANN / f"待标注_{stage}.csv"
        if not path.exists():
            continue
        rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig")) if any(r[k].strip() for k in r if k[:1] in "CSAV" and " " in k)]
        if not rows:
            continue
        per_dim = defaultdict(lambda: ([], []))
        red_h, red_m, ver_h, ver_m = [], [], [], []
        for r in rows:
            f = res_dir / f"{r['case_id']}.json"
            if not f.exists():
                continue
            res = json.loads(f.read_text())["result"]
            mdims = {d["id"]: d["mean"] for d in res["dimensions"]}
            for d in spec["dimensions"]:
                h = r.get(f"{d['id']} {d['name']}", "").strip()
                if h and mdims.get(d["id"]) is not None:
                    per_dim[d["id"]][0].append(int(float(h)))
                    per_dim[d["id"]][1].append(int(round(mdims[d["id"]])))
            hr = {x.strip().upper() for x in r["命中红线（填 R 编号，逗号分隔；无则留空）"].replace("，", ",").split(",") if x.strip()}
            mr = {x["id"] for x in res["redlines"] if x["status"] == "命中"}
            red_h.append(bool(hr))
            red_m.append(bool(mr))
            v = r["结论（通过/修改后通过/驳回）"].strip()
            if v in VERDICTS:
                ver_h.append(v)
                ver_m.append(next(x for x in VERDICTS if res["verdict"].startswith(x)))
        L += [f"## {spec['name']}（{len(red_h)} 例）", "", "| 维度 | 样本 | 加权 κ | 完全一致 | ±1 分一致 | 人工均分 | 模型均分 |", "|---|---|---|---|---|---|---|"]
        for d in spec["dimensions"]:
            h, m = per_dim[d["id"]]
            if not h:
                continue
            k = qwk(h, m)
            L.append(f"| {d['id']} {d['name']} | {len(h)} | {k:.2f} | {sum(x == y for x, y in zip(h, m)) / len(h):.0%} | "
                     f"{sum(abs(x - y) <= 1 for x, y in zip(h, m)) / len(h):.0%} | {sum(h) / len(h):.2f} | {sum(m) / len(m):.2f} |" if k is not None else f"| {d['id']} | {len(h)} | — | | | | |")
        kr = kappa(red_h, red_m)
        kv = kappa(ver_h, ver_m)
        L += ["", f"- 是否命中红线：κ = {kr:.2f}" if kr is not None else "- 是否命中红线：样本不足",
              f"- 结论（三分类）：κ = {kv:.2f}，一致率 {sum(x == y for x, y in zip(ver_h, ver_m)) / len(ver_h):.0%}" if kv is not None else "- 结论：样本不足", ""]
    out = ANN / f"一致性报告_{args.run}.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--n", type=int, default=12)
    e.add_argument("--seed", type=int, default=7)
    a = sub.add_parser("agree")
    a.add_argument("--run", required=True)
    args = ap.parse_args()
    {"export": export, "agree": agree}[args.cmd](args)


if __name__ == "__main__":
    main()
