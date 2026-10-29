"""基准工具链：human_agreement.export()（待标注表）、run_benchmark.load_labels() / run_all() / 多次采样统计。

export 和 load_labels 读真实数据集，期望值用独立写法从 labels.jsonl 现算，不依赖产品代码。
"""
import csv
import json
from collections import Counter
from types import SimpleNamespace

import pytest

import human_agreement as ha
import run_benchmark as rb
from bugs import bug

LABELS = [json.loads(x) for x in (rb.HERE / "dataset" / "labels.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
BY_ID = {l["case_id"]: l for l in LABELS}
STAGES = ["creative", "storyboard", "asset", "video"]
RED_COL = "命中红线（填 R 编号，逗号分隔；无则留空）"


# ---------- human_agreement.export ----------

@pytest.fixture
def export(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ha, "ANN", tmp_path)

    def run(n=12, seed=7):
        ha.export(SimpleNamespace(n=n, seed=seed))
        out = capsys.readouterr().out
        tables = {}
        for st in STAGES:
            with open(tmp_path / f"待标注_{st}.csv", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            with open(tmp_path / f"对照表_{st}.csv", encoding="utf-8-sig", newline="") as f:
                key = dict(list(csv.reader(f))[1:])
            # ids 是对照表还原出的 case_id；rows 是标注员看到的原样内容（盲号）
            tables[st] = {"header": rows[0], "rows": rows[1:], "ids": [key[r[0]] for r in rows[1:]], "key": key}
        return tables, out
    return run


def test_export_header_matches_rubric(export, rubric):
    tables, _ = export()
    for st, t in tables.items():
        dims = [f"{d['id']} {d['name']}" for d in rubric["stages"][st]["dimensions"]]
        assert t["header"] == ["case_id", "材料（相对 benchmark 目录）", "参考材料"] + dims + [
            RED_COL, "结论（通过/修改后通过/驳回）", "备注", "标注人"]
        assert all(len(r) == len(t["header"]) for r in t["rows"])
        # 打分、红线、结论、备注、标注人全部留空给标注员
        assert all(not any(r[3:]) for r in t["rows"])


def test_export_rows_are_test_split_unique_and_materials_match(export):
    tables, _ = export()
    for st, t in tables.items():
        assert len(set(t["ids"])) == len(t["ids"])
        for r in t["rows"]:
            l = BY_ID[t["key"][r[0]]]
            assert l["stage"] == st and l["split"] == "test"
            names = lambda paths: [p.rsplit("/", 1)[-1] for p in paths]
            got_files, got_ctx = r[1].split(" ; "), [x for x in r[2].split(" ; ") if x]
            assert names(got_files) == names(l["inputs"]["files"])
            assert names(got_ctx) == names(l["inputs"].get("context", []))
            for p, src in zip(got_files + got_ctx, l["inputs"]["files"] + l["inputs"].get("context", [])):
                assert p.startswith(f"{ha.ANN.name}/材料/{r[0]}/") and ".." not in p, p
                # 图片 / 视频不进版本库（.gitignore，build_dataset.py 重新生成），只检查文本材料复制过来了、内容一致
                if not p.endswith((".png", ".mp4")):
                    copied = ha.ANN / p.split("/", 1)[1]
                    assert copied.read_bytes() == (rb.HERE / src).read_bytes(), p


def test_export_prints_redline_numbering(export, rubric):
    _, out = export()
    for st in STAGES:
        reds = rubric["stages"][st]["redlines"]
        line = next(x for x in out.splitlines() if f"待标注_{st}.csv" in x)
        assert line.endswith("红线：" + "；".join(f"R{i} {r}" for i, r in enumerate(reds, 1)))


def test_export_stratified_by_kind(export):
    tables, _ = export(n=12)
    for st, t in tables.items():
        kinds = Counter(BY_ID[c]["kind"] for c in t["ids"])
        assert kinds["base"] == 3 and kinds["redline"] == 4, (st, kinds)
        assert kinds["invariance"] == (1 if st != "video" else 0), (st, kinds)


@pytest.mark.parametrize("n,st", [
    (12, "creative"), (12, "storyboard"), (12, "asset"), (6, "creative"),
    (12, "video"),  # 成片没有不变性变体，空出的名额补给其他用例
    (3, "creative"),
    (1, "creative"),
])
def test_export_exports_exactly_n(export, n, st):
    tables, _ = export(n=n)
    assert len(tables[st]["ids"]) == n


def test_export_deterministic_per_seed(export):
    a, _ = export(seed=7)
    b, _ = export(seed=7)
    c, _ = export(seed=8)
    assert all(a[st]["ids"] == b[st]["ids"] for st in STAGES)
    assert any(a[st]["ids"] != c[st]["ids"] for st in STAGES)


def test_export_shuffles_kinds(export):
    # 不打乱的话行按 base/redline/invariance/quality 成块排列，标注员能按位置猜出类型
    tables, _ = export()
    order = [BY_ID[c]["kind"] for c in tables["creative"]["ids"]]
    blocks = [k for i, k in enumerate(order) if i == 0 or order[i - 1] != k]
    assert len(blocks) > len(set(order))


def test_export_is_blind(export):
    tables, _ = export()
    for t in tables.values():
        for r in t["rows"]:
            variant = BY_ID[t["key"][r[0]]]["variant"]
            assert variant not in r[0] and variant not in r[1] and variant not in r[2], r[:3]


def test_export_roundtrip_through_agree(export, tmp_path, monkeypatch):
    """导出的表填上分数后，agree() 能读出全部行。"""
    tables, _ = export()
    t = tables["creative"]
    monkeypatch.setattr(ha, "HERE", tmp_path)
    res = tmp_path / "results" / "r"
    assert all(r[0] not in BY_ID for r in t["rows"])  # 表里是盲号，agree() 要靠对照表找回结果
    res.mkdir(parents=True)
    filled = []
    for r in t["rows"]:
        filled.append(r[:3] + ["4"] * (len(r) - 7) + ["", "通过", "", "张"])
        dims = [{"id": h.split()[0], "mean": 4} for h in t["header"][3:-4]]
        (res / f"{t['key'][r[0]]}.json").write_text(json.dumps({"result": {"verdict": "通过", "redlines": [], "dimensions": dims}}),
                                          encoding="utf-8")
    with open(tmp_path / "待标注_creative.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows([t["header"]] + filled)
    for st in STAGES[1:]:
        (tmp_path / f"待标注_{st}.csv").unlink()
    ha.agree(SimpleNamespace(run="r"))
    md = (tmp_path / "一致性报告_r.md").read_text(encoding="utf-8")
    assert f"（{len(filled)} 例）" in md


# ---------- run_benchmark.load_labels ----------

def ns(stages=None, scenarios=None, variants=None, split=None):
    return SimpleNamespace(stages=stages, scenarios=scenarios, variants=variants, split=split)


SPECS = [
    {},
    {"split": "dev"},
    {"split": "test"},
    {"stages": ["asset"]},
    {"stages": ["creative", "video"], "split": "dev"},
    {"scenarios": ["S03", "S07"]},
    {"variants": ["base"]},
    {"variants": ["base", "cr_infeasible"], "stages": ["creative"]},
    {"stages": ["video"], "scenarios": ["S01"], "variants": ["base"], "split": "test"},
    {"stages": [], "scenarios": [], "variants": []},  # 空列表等于不过滤
    {"variants": ["no_such_variant"]},
]


def expected(spec):
    return [l["case_id"] for l in LABELS
            if (not spec.get("stages") or l["stage"] in spec["stages"])
            and (not spec.get("scenarios") or l["scenario"] in spec["scenarios"])
            and (not spec.get("variants") or l["variant"] in spec["variants"])
            and (not spec.get("split") or l["split"] == spec["split"])]


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: json.dumps(s) if s else "all")
def test_load_labels_filters(spec):
    assert [l["case_id"] for l in rb.load_labels(ns(**spec))] == expected(spec)


def test_load_labels_known_counts():
    assert len(rb.load_labels(ns())) == 420
    assert len(rb.load_labels(ns(split="dev"))) == 105
    assert len(rb.load_labels(ns(split="dev", stages=["asset"]))) == 20


# ---------- run_benchmark.run_all ----------

@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "HERE", tmp_path)
    monkeypatch.setattr(rb.video_review, "load_api_key", lambda: "sk-x")
    calls = []

    def fake_run_case(lab, args, key):
        calls.append(lab["case_id"])
        if lab["case_id"] == "boom":
            raise RuntimeError("模型挂了")
        return {"case_id": lab["case_id"], "seconds": 0.1, "result": {"verdict": "通过", "total": 4.0}}
    monkeypatch.setattr(rb, "run_case", fake_run_case)
    args = SimpleNamespace(name="t", workers=3)
    return tmp_path / "results" / "t", calls, lambda labels: rb.run_all(labels, args)


def test_run_all_isolates_failures(runner, capsys):
    out, calls, run = runner
    run([{"case_id": c} for c in ("a", "boom", "b")])
    assert sorted(calls) == ["a", "b", "boom"]
    assert sorted(p.stem for p in out.glob("*.json")) == ["a", "b"]  # 失败的不落盘，下次重跑会补
    err = capsys.readouterr().err
    assert "boom 失败：模型挂了" in err and "RuntimeError" in err


def test_run_all_skips_cached_and_retries_failed(runner):
    out, calls, run = runner
    run([{"case_id": c} for c in ("a", "boom", "b")])
    calls.clear()
    run([{"case_id": c} for c in ("a", "boom", "b", "c")])
    assert sorted(calls) == ["boom", "c"]


# ---------- 多次采样统计 ----------

def multi_result(spreads, runs):
    return {"result": {"total": 4.0, "verdict": "通过", "redlines": [],
                       "dimensions": [{"id": f"C{i}", "mean": 4, "spread": s} for i, s in enumerate(spreads, 1)]},
            "raw_runs": [{}] * runs, "usage": {"prompt_tokens": 1}, "seconds": 1.0}


def score_one(tmp_path, monkeypatch, res, runs):
    monkeypatch.setattr(rb, "HERE", tmp_path)
    out = tmp_path / "results" / "t"
    out.mkdir(parents=True)
    (out / "base.json").write_text(json.dumps(res), encoding="utf-8")
    lab = {"case_id": "base", "scenario": "S01", "split": "test", "stage": "creative", "variant": "base", "kind": "base",
           "description": "", "base_case_id": None,
           "expect": {"redlines": [], "target": [], "no_redline": True, "verdict_not": []}}
    rb.score([lab], SimpleNamespace(name="t", model="m", runs=runs))
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    return {m["name"]: m["values"].get("creative") for m in s["metrics"]}


def test_spread_metrics_with_multiple_runs(tmp_path, monkeypatch):
    m = score_one(tmp_path, monkeypatch, multi_result([0, 2, 1, None], runs=3), runs=3)
    assert m["多次采样分歧 ≥2 的维度占比"] == "33% (1/3)"  # spread 为 None 的维度不计
    assert m["多次采样平均极差"] == "1.00"


def test_spread_metrics_absent_with_single_run(tmp_path, monkeypatch):
    m = score_one(tmp_path, monkeypatch, multi_result([0, 2, 1], runs=1), runs=1)
    assert "多次采样分歧 ≥2 的维度占比" not in m and "多次采样平均极差" not in m
