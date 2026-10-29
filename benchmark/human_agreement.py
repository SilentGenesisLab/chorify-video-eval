#!/usr/bin/env python3
"""人工标注：导出待标注表 → 专家填写 → 计算评审器与人工的一致性。

python human_agreement.py export --n 12          # 每个关卡抽 12 例，生成 annotation/待标注_<关卡>.csv
python human_agreement.py agree --run run1       # 读取已填写的 CSV，与 results/run1 对比

盲标：待标注表里只有盲号（如 creative-03）和复制到 annotation/材料/<盲号>/ 下的材料，看不出变体类型；
盲号与 case_id 的对照在 annotation/对照表_<关卡>.csv，不要发给标注员。
"""
import argparse
import csv
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ANN = HERE / "annotation"
VERDICTS = ["通过", "修改后通过", "驳回"]


def rubric():
    return json.loads((ROOT / "rubrics.json").read_text(encoding="utf-8"))


def export(args):
    labels = [json.loads(x) for x in (HERE / "dataset" / "labels.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rb = rubric()
    rng = random.Random(args.seed)
    ANN.mkdir(exist_ok=True)
    for stage, spec in rb["stages"].items():
        pool = [l for l in labels if l["stage"] == stage and l["split"] == "test"]
        by_kind = defaultdict(list)
        for l in pool:
            by_kind[l["kind"]].append(l)
        # 分层抽样：红线约 1/3，基准最多 3 例、不变性最多 1 例，其余给质量用例；合计恰好 n 例
        red = args.n // 3
        base = min(3, args.n - red)
        quota = {"base": base, "redline": red, "invariance": min(1, args.n - red - base)}
        quota["quality"] = args.n - sum(quota.values())
        picked = []
        for kind, k in quota.items():
            picked += rng.sample(by_kind[kind], min(k, len(by_kind[kind])))
        # 某类不够（如成片没有不变性变体）时，空出的名额从剩下的用例里补
        rest = [l for l in pool if l not in picked]
        picked += rng.sample(rest, min(args.n - len(picked), len(rest)))
        rng.shuffle(picked)  # 打乱顺序，按位置也猜不出类型
        dims = [f"{d['id']} {d['name']}" for d in spec["dimensions"]]
        reds = "；".join(f"R{i + 1} {r}" for i, r in enumerate(spec["redlines"]))
        path = ANN / f"待标注_{stage}.csv"
        key = []
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "材料（相对 benchmark 目录）", "参考材料"] + dims + ["命中红线（填 R 编号，逗号分隔；无则留空）", "结论（通过/修改后通过/驳回）", "备注", "标注人"])
            for i, l in enumerate(picked, 1):
                blind = f"{stage}-{i:02d}"
                key.append((blind, l["case_id"]))
                files = [blind_copy(x, blind, "") for x in l["inputs"]["files"]]
                ctx = [blind_copy(x, blind, "参考") for x in l["inputs"].get("context", [])]
                w.writerow([blind, " ; ".join(files), " ; ".join(ctx)] + [""] * len(dims) + ["", "", "", ""])
        with open(ANN / f"对照表_{stage}.csv", "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows([["盲号", "case_id"]] + key)
        print(f"{path}（{len(picked)} 例）　红线：{reds}")


def blind_copy(rel, blind, sub):
    """把材料复制到 annotation/材料/<盲号>/[sub/] 下，返回相对 benchmark 目录的路径。原目录名带变体名，不能直接给标注员。"""
    dst = ANN / "材料" / blind / sub / Path(rel).name
    dst.parent.mkdir(parents=True, exist_ok=True)
    src = HERE / rel
    if src.is_file():  # 图片和视频不进版本库，没生成时只给路径
        shutil.copyfile(src, dst)
    return Path(ANN.name, "材料", blind, sub, Path(rel).name).as_posix()


def load_key():
    """盲号 → case_id；没有对照表时（旧版导出）按原样使用。"""
    key = {}
    for p in ANN.glob("对照表_*.csv"):
        with open(p, encoding="utf-8-sig", newline="") as f:
            key.update({r["盲号"]: r["case_id"] for r in csv.DictReader(f)})
    return key


def qwk(a, b, k=5):
    """二次加权 Cohen's kappa，评分 1..k。"""
    n = len(a)
    if n == 0:
        return None
    if bad := [x for x in (*a, *b) if not (isinstance(x, int) and 1 <= x <= k)]:
        raise ValueError(f"评分必须是 1..{k} 的整数：{bad[:5]}")
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
    key = load_key()
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
            f = res_dir / f"{key.get(r['case_id'], r['case_id'])}.json"
            if not f.exists():
                continue
            res = json.loads(f.read_text(encoding="utf-8"))["result"]
            mdims = {d["id"]: d["mean"] for d in res["dimensions"]}
            for d in spec["dimensions"]:
                h = r.get(f"{d['id']} {d['name']}", "").strip()
                if h and mdims.get(d["id"]) is not None:
                    per_dim[d["id"]][0].append(int(float(h)))
                    per_dim[d["id"]][1].append(int(mdims[d["id"]] + 0.5))  # 四舍五入（round() 是银行家舍入，2.5→2）
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
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
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
