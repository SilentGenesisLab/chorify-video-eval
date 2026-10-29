"""B 层评分器自身的单元测试：统计工具、独立聚合 view、几个容易写错的指标语义（B34/B36/B37/B38）。

不调用模型，随 A 层一起跑：.venv/Scripts/python -X utf8 -m pytest tests/bench
"""
import random

import pytest

from common import dim_ids, half_up, mcnemar_exact, qwk, rate, redline_ids, RUBRIC, wilson
from score import metrics, monotonicity, parse_hit, parse_score, view

import video_review


def run(stage, scores, hits=(), drop=()):
    """一次采样：scores 是单个整数（所有维度同分）或 {维度: 分}；drop 里的维度不输出（模拟漏答）。"""
    if isinstance(scores, int):
        scores = {d: scores for d in dim_ids(stage)}
    return {"dimensions": [{"id": d, "score": s, "evidence": ""} for d, s in scores.items() if d not in drop],
            "redlines": [{"id": r, "hit": r in hits, "evidence": ""} for r in redline_ids(stage)]}


def res(stage, runs):
    return {"raw_runs": runs, "result": {}, "usage": {}, "runs": len(runs)}


def lab(cid, stage="creative", kind="base", base=None, redlines=(), target=(), variant="base"):
    return {"case_id": cid, "stage": stage, "split": "test", "kind": kind, "variant": variant, "base_case_id": base,
            "expect": {"redlines": list(redlines), "no_redline": not redlines, "target": list(target)},
            "inputs": {"files": []}}


# ---------------- 统计工具 ----------------

def test_wilson():
    assert wilson(0, 0) == (None, None)
    lo, hi = wilson(5, 10)
    assert 0 <= lo < 0.5 < hi <= 1
    assert wilson(10, 10)[1] == 1.0 and wilson(0, 10)[0] == 0.0


def test_rate_ignores_none():
    assert rate([True, None, False])["n"] == 2


def test_half_up_not_bankers():
    assert [half_up(x) for x in (2.5, 3.5, 2.49, 4.5)] == [3, 4, 2, 5]


def test_qwk():
    assert qwk([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 1.0
    assert qwk([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) < 0
    with pytest.raises(ValueError):
        qwk([0, 3], [3, 3])
    with pytest.raises(ValueError):
        qwk([3], [3, 3])


def test_mcnemar():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(0, 6) == pytest.approx(2 / 64)


# ---------------- 独立聚合 ----------------

@pytest.mark.parametrize("n_hit,n,hit,suspect", [(2, 3, True, False), (1, 3, False, True), (1, 2, False, True),
                                                 (2, 2, True, False), (0, 3, False, False)])
def test_view_redline_majority(n_hit, n, hit, suspect):
    runs = [run("creative", 4, hits=("R1",) if i < n_hit else ()) for i in range(n)]
    h = view(lab("x"), res("creative", runs))["hits"]["R1"]
    assert (h["hit"], h["suspect"], h["any"]) == (hit, suspect, n_hit > 0)


def test_view_missing_dimension_counted_not_dropped():
    d0 = dim_ids("creative")[0]
    v = view(lab("x"), res("creative", [run("creative", 4), run("creative", 2, drop=(d0,))]))
    assert v["dims"][d0]["missing"] == 1 and v["dims"][d0]["mean"] == 4


def test_view_matches_product_aggregate():
    rnd = random.Random(7)
    for stage in ["creative", "storyboard", "asset", "video"]:
        for _ in range(150):
            runs = [run(stage, {d: rnd.choice([2, 3, 3, 4, 4, 5]) for d in dim_ids(stage)},
                        hits=[r for r in redline_ids(stage) if rnd.random() < 0.15]) for _ in range(3)]
            p = video_review.aggregate(stage, RUBRIC, runs)
            v = view(lab("x", stage), res(stage, runs))
            # 产品先把各维均分舍入到 2 位再加权，view 用未舍入均分：总分可差 0.01，与 product_aggregate_diff 的容差一致
            assert p["verdict"] == v["verdict"] and abs(p["total"] - v["total"]) <= 0.01 + 1e-9


# ---------------- 指标语义 ----------------

def M(labels, results):
    return metrics(results, {l["case_id"]: l for l in labels})[0]


def test_invariance_float_epsilon_b34():
    # 1.3 - 1.0 = 0.30000000000000004：Δ 正好 0.3 应算通过，0.4 不通过
    base = res("creative", [run("creative", 1)] * 10)
    same = res("creative", [run("creative", 1)] * 7 + [run("creative", 2)] * 3)
    off = res("creative", [run("creative", 1)] * 6 + [run("creative", 2)] * 4)
    labels = [lab("b"), lab("i1", kind="invariance", base="b", variant="inv_a"),
              lab("i2", kind="invariance", base="b", variant="inv_b")]
    m = M(labels, {"b": base, "i1": same, "i2": off})
    assert (m["b4.invariance"]["k"], m["b4.invariance"]["n"]) == (1, 2)


def test_extra_hits_on_redline_cases_b36():
    labels = [lab("r1", kind="redline", redlines=["R2"]), lab("r2", kind="redline", redlines=["R2"])]
    m = M(labels, {"r1": res("creative", [run("creative", 2, hits=("R2", "R3"))] * 3),
                   "r2": res("creative", [run("creative", 2, hits=("R2",))] * 3)})
    assert m["b1.recall"]["rate"] == 1.0
    assert (m["b2.extra_hits_on_redline_cases"]["k"], m["b2.extra_hits_on_redline_cases"]["n"]) == (1, 2)


def test_sensitivity_missing_target_b38():
    t = dim_ids("creative")[5]
    labels = [lab("b"), lab("q1", kind="quality", base="b", target=[t]), lab("q2", kind="quality", base="b", target=[t])]
    m = M(labels, {"b": res("creative", [run("creative", 4)] * 3),
                   "q1": res("creative", [run("creative", 4, drop=(t,))] * 3),
                   "q2": res("creative", [run("creative", {**{d: 4 for d in dim_ids("creative")}, t: 2})] * 3)})
    assert m["b3.sensitivity_missing"]["n"] == 1
    assert (m["b3.sensitivity"]["k"], m["b3.sensitivity"]["n"]) == (1, 1)


def test_coverage_reports_missing_b37():
    labels = [lab("b"), lab("q1", kind="quality", base="b", target=["C1"])]
    m = M(labels, {"q1": res("creative", [run("creative", 3)] * 3)})
    assert m["data.missing_cases"] == ["b"] and m["data.bases_missing"]["n"] == 1


# ---------------- 复审修正（宽进的解析、单调方向、单次采样、到底排除、轮间缺失）----------------

@pytest.mark.parametrize("raw,want", [(4, 4), (4.0, 4), ("4", 4), (" 4.0 ", 4), (3.5, None), (True, None),
                                      (0, None), (6, None), ("四", None), (None, None)])
def test_parse_score_accepts_integral_floats_b04(raw, want):
    assert parse_score(raw) == want


@pytest.mark.parametrize("raw,want", [(True, True), (False, False), ("false", False), ("False", False), ("否", False),
                                      ("true", True), ("命中", True), (None, None), (1, None), ("maybe", None)])
def test_parse_hit_does_not_bool_strings_b08(raw, want):
    assert parse_hit(raw) == want


def test_view_float_and_string_outputs():
    runs = [{"dimensions": [{"id": d, "score": 4.0} for d in dim_ids("creative")],
             "redlines": [{"id": r, "hit": "false"} for r in redline_ids("creative")]}] * 3
    v = view(lab("x"), res("creative", runs))
    assert v["missing_dims"] == [] and v["total"] == 4.0 and v["hits_set"] == set() and v["verdict"] == "通过"


def fake_v(dim=None, hit=None):
    return {"dims": {"C6": {"mean": dim}}, "hits": {"R2": {"any": hit}}}


@pytest.mark.parametrize("levels,ok", [([False, False, True, True], True), ([False, True, True], True),
                                       ([True, False, True], False), ([False, True, False], False),
                                       ([False, None, True], False)])
def test_monotone_redline_escalates(levels, ok):
    V = {f"c{i}": fake_v(hit=h) for i, h in enumerate(levels)}
    s = {"x": {"metric": "redline", "target": "R2", "cases": list(V)}}
    assert monotonicity(s, V)["x"]["ok"] is ok


@pytest.mark.parametrize("levels,ok,strict", [([4, 3.5, 2], True, True), ([4, 4, 3.5], True, False),
                                              ([4, 2, 3], False, True)])
def test_monotone_dim_decreases(levels, ok, strict):
    V = {f"c{i}": fake_v(dim=x) for i, x in enumerate(levels)}
    m = monotonicity({"x": {"metric": "dim", "target": "C6", "cases": list(V)}}, V)["x"]
    assert (m["ok"], m["strict_drop"]) == (ok, strict)


def test_unstable_cases_skips_single_run():
    labels = [lab("a"), lab("b")]
    m = M(labels, {"a": res("creative", [run("creative", 3)]), "b": res("creative", [run("creative", 3)])})
    assert m["b5.unstable_cases"]["n"] == 0 and m["b5.unstable_cases"]["rate"] is None


def test_sensitivity_floor_uses_every_target():
    t1, t2 = dim_ids("creative")[0], dim_ids("creative")[1]
    base = {**{d: 4 for d in dim_ids("creative")}, t1: 1}
    labels = [lab("b"), lab("q", kind="quality", base="b", target=[t1, t2])]
    m = M(labels, {"b": res("creative", [run("creative", base)] * 3),
                   "q": res("creative", [run("creative", {**base, t2: 2})] * 3)})
    assert m["b3.sensitivity_floor_excluded"]["n"] == 0
    assert (m["b3.sensitivity"]["k"], m["b3.sensitivity"]["n"]) == (1, 1)


def test_round_delta_skips_missing_total():
    labels = [lab("a"), lab("b")]
    r1 = {"a": res("creative", [run("creative", 4)]), "b": res("creative", [run("creative", 4)])}
    r2 = {"a": res("creative", [run("creative", 4)]), "b": res("creative", [{"dimensions": [], "redlines": []}])}
    m = metrics(r1, {l["case_id"]: l for l in labels}, compare=r2)[0]
    assert m["b5.round_total_delta"]["n"] == 1 and m["b5.round_total_delta"]["mean"] == 0


def test_aggregate_diff_catches_shared_float_bug_b04():
    """模型输出 4.0 时，独立聚合照常计分；产品若把它当缺失（B04），product_aggregate_diff 必须报出来。"""
    runs = [{"dimensions": [{"id": d, "score": 4.0} for d in dim_ids("creative")],
             "redlines": [{"id": r, "hit": False} for r in redline_ids("creative")]}] * 3
    m = M([lab("a")], {"a": res("creative", runs)})
    p = video_review.aggregate("creative", RUBRIC, runs)
    assert m["product_aggregate_diff"]["n"] == (0 if (p["verdict"], p["total"]) == ("通过", 4.0) else 1)


@pytest.mark.parametrize("text,want", [("镜8落版字幕", ["8"]), ("镜 3 界面", ["3"]), ("镜1→4→6", ["1"]),
                                       ("第6镜22-26秒仪表盘", []), ("第5镜12个月硬币", []), ("旁白每镜11–13字", []),
                                       ("但镜5缺失导致", []), ("镜6 若存在落版", []), ("单镜 24 秒", []), ("分镜30s", []),
                                       ("镜4 11–16s 航拍", ["4"])])
def test_shot_ref_regex(text, want):
    import evidence
    assert evidence.SHOT_RE.findall(text) == want
