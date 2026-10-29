"""B6 标注：生成盲标包、汇总标注。

标注人：Claude（不是人工）。为了减少锚定，标注时只看材料、不知道用例 ID 和变体名：
  python tests/bench/annotate.py --build              # 复制材料到 annotations/packets/A01…，映射写 key.json（不打印）
  在 packets/Axx/ 下写 scores.json：{"dimensions": {"C1": 3, …}, "redlines_hit": ["R2"], "comment": "…"}
  python tests/bench/annotate.py --collect            # 按 key.json 还原 case_id，写到 annotations/<case_id>.json
  python tests/bench/score.py --results …             # 自动读入 annotations/

用例集：4 个测试场景 × 创意（基准 + 套路化 + 无 CTA）+ 分镜（基准 + 镜头单一 + 删 CTA）。
"""
import argparse
import json
import shutil

from common import BENCH, data_root, dim_ids, load_main, redline_ids, resolve

ANNOT = BENCH / "annotations"
PICK = {"creative": ["base", "cr_cliche", "cr_no_cta"], "storyboard": ["base", "sb_monotone", "sb_no_cta"]}
SCENARIOS = ["S03", "S04", "S06", "S08"]


def selected():
    labs = {l["case_id"]: l for l in load_main()}
    return [labs[f"{s}_{st}_{v}"] for s in SCENARIOS for st, vs in PICK.items() for v in vs]


def build():
    if (ANNOT / "key.json").exists():
        raise SystemExit("annotations/key.json 已存在：先删掉再重建，避免和已有标注错位")
    key, i = {}, 0
    for lab in selected():
        i += 1
        anon = f"A{i:02d}"
        d = ANNOT / "packets" / anon
        d.mkdir(parents=True, exist_ok=True)
        for f in lab["inputs"]["files"] + lab["inputs"].get("context", []):
            src = resolve(f)
            shutil.copy(src, d / src.name)
        (d / "README.txt").write_text(
            f"评审对象：{lab['stage']}\n"
            f"待评审材料是本目录下 {', '.join(resolve(f).name for f in lab['inputs']['files'])}；"
            f"其余文件是前序关卡的参考材料。\n"
            f"请按 rubrics.json 中 {lab['stage']} 关卡的维度与红线打分（整数 1–5），写进 scores.json。\n", encoding="utf-8")
        (d / "scores.json").write_text(
            json.dumps({"stage": lab["stage"], "dimensions": {d0: 0 for d0 in dim_ids(lab["stage"])},
                        "redlines_hit": [], "comment": ""}, ensure_ascii=False, indent=1), encoding="utf-8")
        key[anon] = lab["case_id"]
    ANNOT.mkdir(exist_ok=True)
    (ANNOT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"生成 {len(key)} 个盲标包：{ANNOT / 'packets'}")


def collect():
    key = json.loads((ANNOT / "key.json").read_text(encoding="utf-8"))
    n = 0
    for anon, cid in key.items():
        p = ANNOT / "packets" / anon / "scores.json"
        s = json.loads(p.read_text(encoding="utf-8"))
        # 维度还有 0 = 没标完，跳过；redlines_hit 为空列表也是有效标注（"无红线"），要保留
        if not s.get("dimensions") or any(v == 0 for v in s["dimensions"].values()):
            continue
        s["case_id"] = cid
        s["annotator"] = "Claude（非人工）"
        (ANNOT / f"{cid}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    print(f"汇总 {n} 条标注到 {ANNOT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--collect", action="store_true")
    a = ap.parse_args()
    build() if a.build else collect()
