"""第二轮用例生成入口：写 v2/labels.jsonl 与 v2/meta.json（各子集的序列与 e6 档位），材料在 v2/cases/。

python tests/bench/cases_v2.py                    # 全部生成；已存在的媒体文件跳过
python tests/bench/cases_v2.py --families b9 e2   # 只重新生成部分子集，其他子集的标签保留
python tests/bench/cases_v2.py --check            # 不生成，只校验现有标签的引用和材料

需要真实素材（Z:\\）的 b10 / b13 真实部分 / b15 不在这里；b16 / b19 / b23 / e5 是离线分析（offline.py）；
e7 要先有本轮结果才能按 top_fixes 改写（refine_loop.py）；e8 等专业人员。
"""
import argparse
import json
import sys
import time
from collections import Counter

import shutil

from common import REAL, V2, load_main, load_v2, resolve

import fam_coverage
import fam_cross
import fam_effect
import fam_ext
import fam_gradient
import fam_perception
import fam_redline
import fam_scale
from v2lib import REAL_FAMILIES, Builder

try:  # 真实素材子集（客户材料路径）不进公开仓库，只在本地有
    import fam_real
except ImportError:
    fam_real = None

# 有依赖的放后面：b12 / e2 / e6 引用 b17 的范例，e2 引用 e1，b21（完整集）引用 b18
FAMILIES = {"b9": fam_perception.b9, "b11": fam_redline.b11, "b13": fam_redline.b13, "b14": fam_cross.b14,
            "b17": fam_effect.b17, "b18": fam_scale.b18, "b20": fam_cross.b20, "b21": fam_scale.b21, "b22": fam_scale.b22,
            "b12": fam_gradient.b12, "e1": fam_ext.e1, "e2": fam_ext.e2, "e3": fam_perception.e3, "e4": fam_effect.e4,
            "e6": fam_effect.e6, "b25": fam_coverage.b25,
            **({"b10": fam_real.b10, "b15": fam_real.b15} if fam_real else {})}
# 精简集（默认）：回答"看不看画面""判得对不对"和真实素材；其余子集只在 --full 时生成（STATUS_v2 §1）
OPTIONAL = {"b12", "b14", "b18", "b20", "b22", "e6"}
LABELS, META = V2 / "labels.jsonl", V2 / "meta.json"
REAL_LABELS = REAL / "labels.jsonl"


def load():
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    return load_v2(), meta


def save(labels, meta):
    """合成用例标签进仓库；真实素材用例标签写到仓库外 REAL。"""
    V2.mkdir(parents=True, exist_ok=True)
    REAL.mkdir(parents=True, exist_ok=True)
    syn = [l for l in labels if l["family"] not in REAL_FAMILIES]
    real = [l for l in labels if l["family"] in REAL_FAMILIES]
    LABELS.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in syn), encoding="utf-8")
    REAL_LABELS.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in real), encoding="utf-8")
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def prune(labels):
    """删掉不在当前标签里的用例目录（精简后被删的用例），返回删掉的个数。"""
    keep = {l["case_id"] for l in labels}
    n = 0
    for root in (V2 / "cases", REAL / "cases"):
        if root.is_dir():
            for d in root.iterdir():
                if d.is_dir() and d.name not in keep:
                    shutil.rmtree(d)
                    n += 1
    return n


def refs(c):
    out = [c.get(k) for k in ("a", "b", "vs", "clean")] + (list(c["ids"]) if c["t"] == "order" else [])
    return [x for x in out if x]


def check(labels, meta):
    """引用的用例都存在（本轮或主集测试集），材料文件都在。返回问题列表。"""
    main = {l["case_id"]: l for l in load_main()}
    v2 = {l["case_id"] for l in labels}
    known = v2 | {k for k, l in main.items() if l["split"] == "test"}
    bad = []
    for l in labels:
        for c in l["checks"]:
            bad += [f"{l['case_id']}：{c['key']} 引用了不存在的 {r}" for r in refs(c) if r not in known]
        inp = l["inputs"]
        for f in inp["files"] + inp.get("context", []) + ([inp["transcript"]] if inp.get("transcript") else []):
            if not resolve(f).exists():
                bad.append(f"{l['case_id']}：缺材料 {f}")
    for fam, m in meta.items():
        for name, s in m.get("series", {}).items():
            bad += [f"序列 {name} 引用了不存在的 {r}" for r in s["ids"] if r not in known]
        bad += [f"档位引用了不存在的 {r}" for r in m.get("tiers", {}) if r not in known]
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", nargs="*", choices=list(FAMILIES))
    ap.add_argument("--full", action="store_true", help="生成完整集（含精简时删掉的子集和组）")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    labels, meta = load()
    if not args.check:
        active = [f for f in FAMILIES if args.full or f not in OPTIONAL]
        todo = [f for f in (args.families or active) if f in active]
        b = Builder(full=args.full)
        for fam in FAMILIES:
            if fam not in todo:
                continue
            t0, n0 = time.time(), len(b.labels)
            b.series, b.tiers = {}, {}
            FAMILIES[fam](b)
            meta[fam] = {"series": b.series, "tiers": b.tiers}
            print(f"[{fam}] {len(b.labels) - n0} 例，{time.time() - t0:.0f}s", file=sys.stderr)
        # 当前不在集合里的子集（精简后删掉的）连标签带材料一起去掉
        keep = [l for l in labels if l["family"] not in todo and l["family"] in active]
        labels = sorted(keep + b.labels, key=lambda l: l["case_id"])
        dup = [c for c, n in Counter(l["case_id"] for l in labels).items() if n > 1]
        if dup:
            sys.exit(f"重复的 case_id（某个用例在两个子集里生成？）：{dup[:5]}")
        meta = {f: m for f, m in meta.items() if f in active}
        save(labels, meta)
        if not args.families:
            print(f"删除不再使用的用例目录 {prune(labels)} 个", file=sys.stderr)
    bad = check(labels, meta)
    c = Counter((l["family"], l["stage"]) for l in labels)
    fams = Counter(l["family"] for l in labels)
    print(f"共 {len(labels)} 例：" + "，".join(f"{f}={n}" for f, n in sorted(fams.items())), file=sys.stderr)
    print("按关卡：" + "，".join(f"{s}={sum(n for (f, st), n in c.items() if st == s)}"
                              for s in ("creative", "storyboard", "asset", "video")), file=sys.stderr)
    for x in bad[:30]:
        print("  ✗ " + x, file=sys.stderr)
    if bad:
        sys.exit(f"{len(bad)} 个问题")


if __name__ == "__main__":
    main()
