"""基准测试的指标计算：score()、qwk()、kappa()、human_agreement.agree()。

指标算错，基准报告的每个数字都不可信，所以用手算的已知答案核对。
"""
import csv
import json
from types import SimpleNamespace

import pytest

import human_agreement as ha
import run_benchmark as rb
from bugs import bug

# ---------- kappa / qwk ----------


def test_kappa_textbook():
    # 维基百科 Cohen's kappa 例：50 份申请，A/B 都同意 20，都不同意 15，κ = 0.4
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert ha.kappa(a, b) == pytest.approx(0.4)


def test_kappa_edges():
    assert ha.kappa([], []) is None
    assert ha.kappa(["a", "b"], ["a", "b"]) == 1
    assert ha.kappa(["a", "a"], ["a", "a"]) is None  # 期望一致率为 1，无定义


def qwk_ref(a, b, k=5):
    """独立实现：1 - Σ(x-y)² / E[(x-y)²]（边际独立）。"""
    n = len(a)
    num = sum((x - y) ** 2 for x, y in zip(a, b))
    den = sum((x - y) ** 2 for x in a for y in b) / n
    return 1 - num / den


@pytest.mark.parametrize("a,b", [
    ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]),
    ([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]),
    ([3, 3, 4, 4, 5, 2], [3, 4, 4, 5, 5, 2]),
    ([1, 1, 2, 5, 5, 3, 4], [2, 1, 2, 4, 5, 3, 3]),
])
def test_qwk_matches_reference(a, b):
    assert ha.qwk(a, b) == pytest.approx(qwk_ref(a, b))


def test_qwk_known_values():
    assert ha.qwk([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1)
    assert ha.qwk([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1)
    assert ha.qwk([], []) is None
    assert ha.qwk([3, 3, 3], [3, 3, 3]) is None


@pytest.mark.parametrize("a,b", [([0, 3], [3, 3]), ([6, 3], [3, 3])])
def test_qwk_rejects_out_of_range(a, b):
    with pytest.raises(ValueError):
        ha.qwk(a, b)


# ---------- human_agreement.agree ----------

@pytest.fixture
def agree_env(tmp_path, monkeypatch, rubric):
    monkeypatch.setattr(ha, "HERE", tmp_path)
    monkeypatch.setattr(ha, "ANN", tmp_path / "annotation")
    monkeypatch.setattr(ha, "rubric", lambda: rubric)
    (tmp_path / "annotation").mkdir()
    (tmp_path / "results" / "r").mkdir(parents=True)
    return tmp_path


def write_case(root, rubric, cid, human, model_mean, verdict="修改后通过"):
    spec = rubric["stages"]["creative"]
    res = {"result": {"verdict": verdict, "redlines": [],
                      "dimensions": [{"id": d["id"], "mean": model_mean} for d in spec["dimensions"]]}}
    (root / "results" / "r" / f"{cid}.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return [cid, "", ""] + [str(human)] * len(spec["dimensions"]) + ["", verdict, "", ""]


def write_csv(root, rubric, rows):
    spec = rubric["stages"]["creative"]
    with open(root / "annotation" / "待标注_creative.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "材料（相对 benchmark 目录）", "参考材料"] + [f"{d['id']} {d['name']}" for d in spec["dimensions"]]
                   + ["命中红线（填 R 编号，逗号分隔；无则留空）", "结论（通过/修改后通过/驳回）", "备注", "标注人"])
        w.writerows(rows)


def test_agree_report_numbers(agree_env, rubric):
    rows = [write_case(agree_env, rubric, "a", 4, 4), write_case(agree_env, rubric, "b", 2, 3),
            write_case(agree_env, rubric, "c", 5, 5)]
    write_csv(agree_env, rubric, rows)
    ha.agree(SimpleNamespace(run="r"))
    md = (agree_env / "annotation" / "一致性报告_r.md").read_text(encoding="utf-8")
    # 人 [4,2,5] 对模型 [4,3,5]：Σ(x-y)² = 1；边际独立下 Σ_ij(x_i-y_j)²/n = 21/3 = 7；QWK = 1 - 1/7 ≈ 0.86
    assert "| C1 策略契合 | 3 | 0.86 | 67% | 100% | 3.67 | 4.00 |" in md
    assert "结论（三分类）：κ = 1.00，一致率 100%" not in md  # 三例结论都相同 → κ 无定义
    assert "结论：样本不足" in md


def test_agree_rounds_half_up(agree_env, rubric):
    write_csv(agree_env, rubric, [write_case(agree_env, rubric, "a", 3, 2.5), write_case(agree_env, rubric, "b", 5, 5)])
    ha.agree(SimpleNamespace(run="r"))
    md = (agree_env / "annotation" / "一致性报告_r.md").read_text(encoding="utf-8")
    assert "| C1 策略契合 | 2 | 1.00 | 100% |" in md


# ---------- run_benchmark.score ----------

def label(cid, kind, *, redlines=(), target=(), base=None, verdict_not=(), stage="creative"):
    return {"case_id": cid, "scenario": "S01", "split": "test", "stage": stage, "variant": cid, "kind": kind,
            "description": cid, "base_case_id": base,
            "expect": {"redlines": list(redlines), "target": list(target), "no_redline": not redlines,
                       "verdict_not": list(verdict_not)}}


def result(total, verdict, dims, hits=(), suspect=()):
    return {"result": {"total": total, "verdict": verdict,
                       "dimensions": [{"id": k, "mean": v, "spread": 0} for k, v in dims.items()],
                       "redlines": [{"id": r, "status": "命中"} for r in hits] + [{"id": r, "status": "疑似（需人审）"} for r in suspect]},
            "raw_runs": [{}], "usage": {"prompt_tokens": 10, "completion_tokens": 1}, "seconds": 1.0}


@pytest.fixture
def bench(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "HERE", tmp_path)
    out = tmp_path / "results" / "t"
    out.mkdir(parents=True)

    def run(cases):
        labels = []
        for lab, res in cases:
            labels.append(lab)
            (out / f"{lab['case_id']}.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        rb.score(labels, SimpleNamespace(name="t", model="m", runs=1))
        return json.loads((out / "summary.json").read_text(encoding="utf-8"))
    return run


def metric(summary, name, stage="creative"):
    return next(m["values"][stage] for m in summary["metrics"] if m["name"] == name)


BASE_DIMS = {"C1": 4, "C2": 4}


def test_score_known_answers(bench):
    s = bench([
        (label("base", "base"), result(4.0, "通过", BASE_DIMS)),
        (label("red_ok", "redline", redlines=["R2"], base="base"), result(4.0, "驳回（命中红线）", BASE_DIMS, hits=["R2"])),
        (label("red_miss", "redline", redlines=["R2"], base="base"), result(4.0, "通过", BASE_DIMS, suspect=["R2"])),
        (label("q_ok", "quality", target=["C1"], base="base"), result(3.6, "修改后通过", {"C1": 2, "C2": 4})),
        (label("q_miss", "quality", target=["C1"], base="base"), result(3.9, "修改后通过", {"C1": 3.5, "C2": 4})),
        (label("inv_ok", "invariance", base="base"), result(4.2, "通过", BASE_DIMS)),
        (label("inv_bad", "invariance", base="base"), result(3.5, "修改后通过", BASE_DIMS)),
        (label("fp", "quality", target=["C2"], base="base"), result(3.0, "驳回（命中红线）", {"C1": 4, "C2": 3}, hits=["R1"])),
    ])
    assert metric(s, "红线召回（命中指定红线）") == "50% (1/2)"
    assert metric(s, "误报率（全部无红线用例）") == "17% (1/6)"
    assert metric(s, "缺陷灵敏度（目标维度降 ≥1 分）") == "67% (2/3)"
    assert metric(s, "不变性（|Δ总分| ≤ 0.3）") == "50% (1/2)"
    assert s["passed"] == 4 and s["cases"] == 8
    failed = {f["case_id"] for f in s["failures"]}
    assert failed == {"red_miss", "q_miss", "inv_bad", "fp"}


def test_score_floor_excluded(bench):
    s = bench([(label("base", "base"), result(2.0, "驳回", {"C1": 1.5, "C2": 4})),
               (label("q", "quality", target=["C1"], base="base"), result(2.0, "驳回", {"C1": 1.5, "C2": 4}))])
    assert metric(s, "目标维度触底（无法再降，已排除）") == "1"
    assert all(m["name"] != "缺陷灵敏度（目标维度降 ≥1 分）" for m in s["metrics"])


def test_invariance_boundary_exactly_0_3(bench):
    s = bench([(label("base", "base"), result(3.7, "修改后通过", BASE_DIMS)),
               (label("inv", "invariance", base="base"), result(4.0, "通过", BASE_DIMS))])
    assert metric(s, "不变性（|Δ总分| ≤ 0.3）") == "100% (1/1)"


@pytest.mark.parametrize("b,v", [
    (1.0, 1.3),
    (1.5, 1.8),
    (2.0, 2.3),
    (4.0, 3.7),
    (2.5, 2.2),
])
def test_invariance_boundary_exactly_0_3_any_value(bench, b, v):
    # 两位小数的总分，|Δ| = 0.30 不论落在哪里都应算不变
    s = bench([(label("base", "base"), result(b, "驳回", BASE_DIMS)),
               (label("inv", "invariance", base="base"), result(v, "驳回", BASE_DIMS))])
    assert metric(s, "不变性（|Δ总分| ≤ 0.3）") == "100% (1/1)"


def test_invariance_just_over_0_3_fails(bench):
    s = bench([(label("base", "base"), result(3.7, "修改后通过", BASE_DIMS)),
               (label("inv", "invariance", base="base"), result(4.01, "通过", BASE_DIMS))])
    assert metric(s, "不变性（|Δ总分| ≤ 0.3）") == "0% (0/1)"


def test_redline_case_extra_hit_is_reported(bench):
    # 注入 R2，评审器命中 R2 之外还命中了 R1：召回成功，但 R1 是误报，应出现在失败清单里
    s = bench([(label("base", "base"), result(4.0, "通过", BASE_DIMS)),
               (label("red", "redline", redlines=["R2"], base="base"),
                result(4.0, "驳回（命中红线）", BASE_DIMS, hits=["R1", "R2"]))])
    assert metric(s, "红线召回（命中指定红线）") == "100% (1/1)"
    assert any(f["case_id"] == "red" and "R1" in f["reason"] for f in s["failures"])


@pytest.mark.parametrize("missing", ["q", "base"])
def test_missing_results_are_reported(bench, tmp_path, missing):
    # 先完整评一次写出两份结果，再删掉其中一份重评
    bench([(label("base", "base"), result(4.0, "通过", BASE_DIMS)),
           (label("q", "quality", target=["C1"], base="base"), result(3.0, "修改后通过", {"C1": 2, "C2": 4}))])
    (tmp_path / "results" / "t" / f"{missing}.json").unlink()
    rb.score([label("base", "base"), label("q", "quality", target=["C1"], base="base")],
             SimpleNamespace(name="t", model="m", runs=1))
    md = (tmp_path / "results" / "t" / "report.md").read_text(encoding="utf-8")
    assert "缺失" in md and f"`{missing}`" in md


def test_secondary_target_none_mean_does_not_crash(bench):
    s = bench([(label("base", "base"), result(4.0, "通过", BASE_DIMS)),
               (label("q", "quality", target=["C1", "C2"], base="base"), result(3.5, "修改后通过", {"C1": 3.5, "C2": None}))])
    assert "q" in {f["case_id"] for f in s["failures"]}


def test_verdict_not_is_checked(bench):
    s = bench([(label("base", "base"), result(4.0, "通过", BASE_DIMS)),
               (label("q", "quality", target=["C1"], base="base", verdict_not=["通过"]), result(4.0, "通过", {"C1": 2, "C2": 4}))])
    assert "q" in {f["case_id"] for f in s["failures"]}
