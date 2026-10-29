"""aggregate：多次采样 → 维度均分、红线投票、总分、结论、人审标记。

判定规则以 rubrics.json 为准：
  命中红线（多数票）→ 驳回；总分 ≥ pass.min_score 且最低维度 ≥ pass.min_dimension → 通过；
  总分 ≥ revise.min_score 且最低维度 ≥ revise.min_dimension → 修改后通过；其他 → 驳回。
"""
import itertools
from fractions import Fraction

import pytest
from hypothesis import given, settings, strategies as st

import video_review as vr
from bugs import bug
from conftest import make_run

STAGES = ["creative", "storyboard", "asset", "video"]


def agg(rubric, stage, *runs):
    return vr.aggregate(stage, rubric, list(runs))


def weights(rubric, stage):
    return [Fraction(str(d["weight"])) for d in rubric["stages"][stage]["dimensions"]]


def find_scores(rubric, stage, pred, values=(1, 2, 3, 4, 5)):
    """在单次采样的整数分组合里找一个满足 pred(精确总分, 最低分) 的例子。"""
    w = weights(rubric, stage)
    for combo in itertools.product(values, repeat=len(w)):
        total = sum(Fraction(s) * x for s, x in zip(combo, w)) / sum(w)
        if pred(total, min(combo)):
            return list(combo)
    raise AssertionError("找不到满足条件的组合")


def oracle(rubric, stage, runs):
    """用精确分数独立实现的判定，作为对照。只接受合法输入（1–5 整数、布尔 hit）。"""
    s = rubric["stages"][stage]
    rules = rubric["verdict_rules"]
    w = weights(rubric, stage)
    means = []
    for d in s["dimensions"]:
        sc = [x["score"] for r in runs for x in r["dimensions"] if x["id"] == d["id"]]
        means.append(Fraction(sum(sc), len(sc)))
    total = sum(m * x for m, x in zip(means, w)) / sum(w)
    low = min(means)
    hit = any(sum(1 for r in runs for x in r["redlines"] if x["id"] == f"R{i + 1}" and x["hit"]) * 2 > len(runs)
              for i in range(len(s["redlines"])))
    if hit:
        return "驳回（命中红线）", total, low
    if total >= rules["pass"]["min_score"] and low >= rules["pass"]["min_dimension"]:
        return "通过", total, low
    if total >= rules["revise"]["min_score"] and low >= rules["revise"]["min_dimension"]:
        return "修改后通过", total, low
    return "驳回", total, low


# ---------- 判定边界 ----------

@pytest.mark.parametrize("stage", STAGES)
def test_all_fours_is_exact_pass_boundary(rubric, stage):
    n = len(rubric["stages"][stage]["dimensions"])
    r = agg(rubric, stage, make_run(rubric, stage, [4] * n))
    assert (r["verdict"], r["total"], r["min_dimension"]) == ("通过", 4.0, 4)


@pytest.mark.parametrize("stage", STAGES)
def test_total_exactly_4_with_min_dimension_3_passes(rubric, stage):
    sc = find_scores(rubric, stage, lambda t, m: t == 4 and m == 3, (3, 4, 5))
    r = agg(rubric, stage, make_run(rubric, stage, sc))
    assert r["total"] == 4.0 and r["verdict"] == "通过"


@pytest.mark.parametrize("stage", STAGES)
def test_total_just_below_4_is_revise(rubric, stage):
    sc = find_scores(rubric, stage, lambda t, m: Fraction(39, 10) <= t < 4 and m >= 3, (3, 4, 5))
    r = agg(rubric, stage, make_run(rubric, stage, sc))
    assert r["total"] < 4.0 and r["verdict"] == "修改后通过"


@pytest.mark.parametrize("stage", STAGES)
def test_high_total_but_one_dimension_2_is_revise(rubric, stage):
    sc = find_scores(rubric, stage, lambda t, m: t >= 4 and m == 2, (2, 5))
    r = agg(rubric, stage, make_run(rubric, stage, sc))
    assert r["verdict"] == "修改后通过"


@pytest.mark.parametrize("stage", STAGES)
def test_any_dimension_1_is_reject_even_with_high_total(rubric, stage):
    sc = find_scores(rubric, stage, lambda t, m: t >= 4 and m == 1, (1, 5))
    r = agg(rubric, stage, make_run(rubric, stage, sc))
    assert r["verdict"] == "驳回"


@pytest.mark.parametrize("stage", STAGES)
def test_total_exactly_3_with_min_2_is_revise(rubric, stage):
    sc = find_scores(rubric, stage, lambda t, m: t == 3 and m == 2, (2, 3, 4))
    r = agg(rubric, stage, make_run(rubric, stage, sc))
    assert r["total"] == 3.0 and r["verdict"] == "修改后通过"


@pytest.mark.parametrize("stage", STAGES)
def test_total_just_below_3_is_reject(rubric, stage):
    sc = find_scores(rubric, stage, lambda t, m: Fraction(29, 10) <= t < 3 and m >= 2, (2, 3, 4))
    r = agg(rubric, stage, make_run(rubric, stage, sc))
    assert r["verdict"] == "驳回"


def test_mean_of_runs_is_used_not_first_run(rubric):
    n = 8
    r = agg(rubric, "creative", make_run(rubric, "creative", [3] * n), make_run(rubric, "creative", [5] * n),
            make_run(rubric, "creative", [4] * n))
    assert r["total"] == 4.0 and all(d["mean"] == 4 and d["scores"] == [3, 5, 4] for d in r["dimensions"])


def test_weighted_total(rubric):
    # C1 权重 0.2 给 1 分，其余 5 分 → 0.2*1 + 0.8*5 = 4.2
    r = agg(rubric, "creative", make_run(rubric, "creative", [1] + [5] * 7))
    assert r["total"] == 4.2 and r["min_dimension"] == 1 and r["verdict"] == "驳回"


# ---------- 红线投票 ----------

@pytest.mark.parametrize("n_runs,n_hit,status", [
    (1, 0, "未命中"), (1, 1, "命中"),
    (2, 1, "疑似（需人审）"), (2, 2, "命中"),
    (3, 1, "疑似（需人审）"), (3, 2, "命中"), (3, 3, "命中"),
    (4, 2, "疑似（需人审）"), (4, 3, "命中"),
    (5, 2, "疑似（需人审）"), (5, 3, "命中"),
])
def test_redline_majority_vote(rubric, n_runs, n_hit, status):
    runs = [make_run(rubric, "video", [5] * len(rubric["stages"]["video"]["dimensions"]), hits=("R2",) if i < n_hit else ()) for i in range(n_runs)]
    r = agg(rubric, "video", *runs)
    r2 = r["redlines"][1]
    assert (r2["status"], r2["hits"]) == (status, f"{n_hit}/{n_runs}")
    assert all(x["status"] == "未命中" for x in r["redlines"] if x["id"] != "R2")
    assert r["verdict"] == ("驳回（命中红线）" if status == "命中" else "通过")
    assert ("R2" in r["needs_human_review"]) is (n_hit > 0)


def test_redline_hit_overrides_perfect_score(rubric):
    r = agg(rubric, "creative", *[make_run(rubric, "creative", [5] * 8, hits=("R2",))] * 3)
    assert r["verdict"] == "驳回（命中红线）" and r["total"] == 5.0


def test_suspected_redline_goes_to_human_but_keeps_verdict(rubric):
    r = agg(rubric, "creative", make_run(rubric, "creative", [5] * 8, hits=("R3",)),
            make_run(rubric, "creative", [5] * 8), make_run(rubric, "creative", [5] * 8))
    assert r["verdict"] == "通过" and r["needs_human_review"] == ["R3"]
    assert r["review_reasons"]["R3"] == "只有 1/3 次采样判命中"
    assert r["redlines"][2]["evidence"] == "R3 证据"


def test_redline_ids_cover_all_rubric_redlines(rubric):
    for stage in STAGES:
        r = agg(rubric, stage, make_run(rubric, stage, [5] * len(rubric["stages"][stage]["dimensions"])))
        assert [x["id"] for x in r["redlines"]] == [f"R{i + 1}" for i in range(len(rubric["stages"][stage]["redlines"]))]
        assert [x["text"] for x in r["redlines"]] == rubric["stages"][stage]["redlines"]


def test_confirmed_redline_requires_human_review(rubric):
    r = agg(rubric, "creative", *[make_run(rubric, "creative", [5] * 8, hits=("R1",))] * 3)
    assert "R1" in r["needs_human_review"]


def test_v3_v4_always_require_human_review(rubric):
    # 框架文档：时间维度只能从相邻帧推断，V3、V4 必须人审复核——与分数和分歧无关
    r = agg(rubric, "video", *[make_run(rubric, "video", [4] * len(rubric["stages"]["video"]["dimensions"]))] * 3)
    assert {"V3", "V4"} <= set(r["needs_human_review"])


def test_v3_v4_are_the_temporal_dimensions(rubric):
    # 防止 B39 的用例因维度编号变化而失效
    names = {d["id"]: d["name"] for d in rubric["stages"]["video"]["dimensions"]}
    assert (names["V3"], names["V4"]) == ("画面质量", "声音质量")


def test_machine_reject_flags_legal_brand_review(rubric):
    # 框架文档：机审"驳回"或命中红线 → 法务/品牌复核。无红线、低分驳回也应有复核标记
    r = agg(rubric, "creative", *[make_run(rubric, "creative", [2] * 8)] * 3)
    assert r["verdict"] == "驳回"
    assert r["needs_human_review"]


@pytest.mark.parametrize("hit", ["true", 1])
def test_truthy_hit_values_count(rubric, hit):
    run = make_run(rubric, "creative", [5] * 8)
    run["redlines"][0]["hit"] = hit
    r = agg(rubric, "creative", run)
    assert r["redlines"][0]["status"] == "命中"


@pytest.mark.parametrize("hit", ["false", 0, False, None])
def test_falsy_hit_values_do_not_count(rubric, hit):
    run = make_run(rubric, "creative", [5] * 8)
    run["redlines"][0]["hit"] = hit
    assert agg(rubric, "creative", run)["redlines"][0]["status"] == "未命中"


def test_duplicate_redline_in_one_run_counts_once(rubric):
    dup = make_run(rubric, "creative", [5] * 8, hits=("R1",),
                   extra_redlines=[{"id": "R1", "hit": True, "evidence": "重复"}])
    r = agg(rubric, "creative", dup, make_run(rubric, "creative", [5] * 8), make_run(rubric, "creative", [5] * 8))
    assert r["redlines"][0]["status"] == "疑似（需人审）"


def test_unjudged_redline_is_flagged(rubric):
    runs = []
    for _ in range(3):
        run = make_run(rubric, "creative", [5] * 8)
        run["redlines"] = [x for x in run["redlines"] if x["id"] != "R1"]
        runs.append(run)
    assert "R1" in agg(rubric, "creative", *runs)["needs_human_review"]


# ---------- 分歧与人审 ----------

@pytest.mark.parametrize("scores,flag", [([3, 4, 5], True), ([4, 4, 5], False), ([3, 3, 3], False), ([2, 4], True)])
def test_spread_ge_2_needs_human(rubric, scores, flag):
    runs = [make_run(rubric, "creative", {"C1": s, **{f"C{i}": 4 for i in range(2, 9)}}) for s in scores]
    r = agg(rubric, "creative", *runs)
    assert r["dimensions"][0]["spread"] == max(scores) - min(scores)
    assert ("C1" in r["needs_human_review"]) is flag


def test_evidence_and_summary_follow_majority_not_outlier(rubric):
    lo = make_run(rubric, "creative", [1] * 8, evidence={"C1": "离群证据"}, summary="离群总评", top_fixes=["离群改法"])
    hi = make_run(rubric, "creative", [5] * 8, evidence={"C1": "多数证据"}, summary="多数总评", top_fixes=["多数改法"])
    r = agg(rubric, "creative", lo, hi, hi)
    assert r["dimensions"][0]["evidence"] == "多数证据"
    assert r["summary"] == "多数总评" and r["top_fixes"] == ["多数改法"]


# ---------- 非法分数 ----------

def test_string_integer_score_accepted(rubric):
    r = agg(rubric, "creative", make_run(rubric, "creative", ["4"] * 8))
    assert r["total"] == 4.0 and r["verdict"] == "通过"


def test_float_integer_score_accepted(rubric):
    r = agg(rubric, "creative", make_run(rubric, "creative", [4.0] * 8))
    assert r["total"] == 4.0 and r["verdict"] == "通过"


@pytest.mark.parametrize("bad", ["4.5", "四", -1, "abc", None, ""])
def test_unparseable_score_needs_human(rubric, bad):
    r = agg(rubric, "creative", make_run(rubric, "creative", [bad] + [5] * 7))
    assert "C1" in r["needs_human_review"]


@pytest.mark.parametrize("bad", [0, 6, 9])
def test_out_of_range_score_rejected(rubric, bad):
    r = agg(rubric, "creative", make_run(rubric, "creative", [bad] + [5] * 7))
    assert bad not in r["dimensions"][0]["scores"]
    assert "C1" in r["needs_human_review"]


def test_missing_dimension_is_flagged(rubric):
    r = agg(rubric, "creative", make_run(rubric, "creative", [5] * 7))  # C8 缺失
    assert "C8" in r["needs_human_review"]


def test_missing_dimension_cannot_pass(rubric):
    # 只给出 7 个 5 分，缺的 C8 不能被「重新归一」藏掉后判通过
    r = agg(rubric, "creative", *[make_run(rubric, "creative", [5] * 7)] * 3)
    assert r["verdict"] not in ("通过", "修改后通过")
    assert r["dimensions"][7]["mean"] is None


def test_missing_dimension_total_uses_full_weight(rubric):
    # C1 权重 0.2 缺失，其余 5 分：按全部权重算 0.8 × 5 = 4.0，而不是重新归一后的 5.0
    r = agg(rubric, "creative", make_run(rubric, "creative", {f"C{i}": 5 for i in range(2, 9)}))
    assert r["total"] == 4.0


def test_all_runs_empty_is_not_a_content_verdict(rubric):
    empty = {"dimensions": [], "redlines": []}
    try:
        r = agg(rubric, "creative", empty, empty, empty)
    except Exception:
        return  # 报错也是可接受的处理
    assert r["verdict"] not in ("通过", "修改后通过", "驳回")


def test_run_without_dimensions_key_does_not_crash(rubric):
    agg(rubric, "creative", {"redlines": []}, make_run(rubric, "creative", [5] * 8))


def test_unknown_dimension_ids_ignored(rubric):
    run = make_run(rubric, "creative", [4] * 8)
    run["dimensions"].append({"id": "ZZ", "score": 1})
    r = agg(rubric, "creative", run)
    assert [d["id"] for d in r["dimensions"]] == [f"C{i}" for i in range(1, 9)] and r["total"] == 4.0


def test_dimension_order_in_output_independent_of_model_order(rubric):
    run = make_run(rubric, "creative", list(range(1, 6)) + [5, 5, 5])
    run["dimensions"].reverse()
    r = agg(rubric, "creative", run)
    assert [d["mean"] for d in r["dimensions"]] == [1, 2, 3, 4, 5, 5, 5, 5]


# ---------- 与精确对照实现比对（性质测试） ----------

def _runs_strategy(rubric, stage):
    nd = len(rubric["stages"][stage]["dimensions"])
    nr = len(rubric["stages"][stage]["redlines"])
    one = st.tuples(st.lists(st.integers(1, 5), min_size=nd, max_size=nd),
                    st.lists(st.booleans(), min_size=nr, max_size=nr))
    return st.lists(one, min_size=1, max_size=5)


@pytest.mark.parametrize("stage", STAGES)
def test_matches_exact_oracle(rubric, stage):
    @settings(max_examples=400, deadline=None)
    @given(_runs_strategy(rubric, stage))
    def check(spec):
        runs = [make_run(rubric, stage, sc, hits={f"R{i + 1}" for i, h in enumerate(hs) if h}) for sc, hs in spec]
        got = vr.aggregate(stage, rubric, runs)
        verdict, total, low = oracle(rubric, stage, runs)
        assert got["verdict"] == verdict
        assert abs(got["total"] - float(total)) <= 0.01
        assert abs(got["min_dimension"] - float(low)) <= 0.005

    check()
