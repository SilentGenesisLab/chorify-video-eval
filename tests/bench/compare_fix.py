"""修复前后对比：同一批用例、同一口径，逐条检查比较两个结果目录。

python tests/bench/compare_fix.py --after results/fix_v2/r1 --families b9 b10 b11 e3 e4 --out results/fix_v2_compare.md

只统计「修复后」目录里真正重跑过的用例，修复前取同一批用例的旧结果，两边分母相同。
检查里引用的比较对象（delta 的 a/b、redline / mention 的 clean）若没有重跑，两边都用旧结果，
在表里标「基准未重跑」：这类差值混了修复前后的评审器，只能参考方向。
"""
import argparse
from collections import defaultdict
from pathlib import Path

from common import RESULTS, load_all, load_v2, rate
from score import load_results, view
from score_v2 import Ctx, judge


def refs(c):
    return [c[k] for k in ("a", "b", "clean") if c.get(k)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default=str(RESULTS / "v2" / "r1"))
    ap.add_argument("--after", required=True)
    ap.add_argument("--also", nargs="*", default=[str(RESULTS / "b1" / "r1")], help="比较对象所在的旧结果目录")
    ap.add_argument("--families", nargs="*")
    ap.add_argument("--out")
    a = ap.parse_args()

    old = {}
    for d in a.also + [a.before]:
        if Path(d).is_dir():
            old.update(load_results(d))
    new_only = load_results(a.after)
    new = {**old, **new_only}
    labels = {l["case_id"]: l for l in load_all()}
    v2 = [l for l in load_v2() if l["case_id"] in new_only and l["case_id"] in old
          and (not a.families or l.get("family") in a.families)]
    cb, ca = Ctx(old, labels), Ctx(new, labels)

    flags = defaultdict(lambda: ([], []))
    stale = defaultdict(bool)
    for l in v2:
        for c in l["checks"]:
            if c["t"] == "corr":
                continue
            ob, _ = judge(c, l["case_id"], cb)
            oa, _ = judge(c, l["case_id"], ca)
            if ob is None or oa is None:
                continue
            flags[c["key"]][0].append(ob)
            flags[c["key"]][1].append(oa)
            stale[c["key"]] |= any(r not in new_only for r in refs(c) if r != l["case_id"])

    fam_n = defaultdict(int)
    for l in v2:
        fam_n[l["family"]] += 1
    L = [f"重跑用例 {len(v2)} 例：" + "、".join(f"{f} {n}" for f, n in sorted(fam_n.items())), "",
         "| 检查 | 修复前 | 修复后 | 变化 | 备注 |", "|---|---|---|---|---|"]
    for k in sorted(flags):
        b, n = rate(flags[k][0]), rate(flags[k][1])
        d = f"{(n['rate'] - b['rate']) * 100:+.0f} 点" if b.get("n") else ""
        L.append(f"| `{k}` | {b['k']}/{b['n']} | {n['k']}/{n['n']} | {d} | {'基准未重跑' if stale[k] else ''} |")

    flips = []
    for l in sorted(v2, key=lambda x: x["case_id"]):
        cid = l["case_id"]
        vb, va = view(l, old[cid]), view(l, new_only[cid])
        if vb["verdict"] != va["verdict"] or vb["hits_set"] != va["hits_set"]:
            flips.append(f"| `{cid}` | {vb['verdict']} {sorted(vb['hits_set']) or ''} {vb['total']} | "
                         f"{va['verdict']} {sorted(va['hits_set']) or ''} {va['total']} |")
    L += ["", f"### 结论或红线变化的用例（{len(flips)} 例）", "", "| 用例 | 修复前 | 修复后 |", "|---|---|---|"] + flips
    text = "\n".join(L) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
