"""第二轮评分器（score_v2）与标签的单元测试：每种 check 的语义、Spearman、定位匹配、三档 κ、标签引用完整。

不调用模型：.venv/Scripts/python -X utf8 -m pytest -c tests/pytest.ini tests/bench/test_score_v2.py
"""
import json

import pytest

from common import V2, dim_ids, load_v2, redline_ids
from score_v2 import Ctx, derived, judge, located, metrics, spearman, times_in
from test_scoring import res as mkres
from test_scoring import run
from v2lib import better, delta, drop, locus, mention, no_rise, order, redline, verdict


def lab(cid, stage="creative", checks=(), family="b9"):
    return {"case_id": cid, "stage": stage, "family": family, "kind": family, "split": "test", "checks": list(checks),
            "expect": {"redlines": [], "target": [], "no_redline": False}, "inputs": {"files": []}}


def ctx(**cases):
    """cases：case_id → [run, …]（creative 关）。"""
    res = {c: mkres("creative", rs) for c, rs in cases.items()}
    return Ctx(res, {c: lab(c) for c in cases})


def test_drop_and_floor():
    c = ctx(base=[run("creative", 4)] * 3, v=[run("creative", {**{d: 4 for d in dim_ids("creative")}, "C1": 2})] * 3,
            low=[run("creative", 1)] * 3)
    assert judge(drop("b9.x", ["C1"], "base"), "v", c) == (True, 2.0)
    assert judge(drop("b9.x", ["C1"], "base", min=2.5), "v", c)[0] is False
    # 比较对象已经是 1 分，降不了 1 分：不可判定，而不是失败
    assert judge(drop("b9.x", ["C1"], "low"), "v", c)[0] is None


def test_no_rise_better_and_total():
    c = ctx(a=[run("creative", 3)] * 3, b=[run("creative", 4)] * 3)
    assert judge(no_rise("b9.x", "total", "a"), "b", c) == (False, 1.0)
    assert judge(no_rise("b9.x", "total", "b"), "a", c) == (True, -1.0)
    assert judge(better("b9.x", ["C3"], "b", "a"), "a", c)[0] is True
    assert judge(better("b9.x", ["C3"], "a", "a"), "a", c)[0] is False  # 相等不算"更好"
    assert judge(delta("b9.x", ["C1"], b="a", lo=-0.5, hi=0.5), "a", c)[0] is True


def test_missing_result_is_undecided():
    c = ctx(a=[run("creative", 3)] * 3)
    assert judge(drop("b9.x", ["C1"], "nope"), "a", c) == (None, None)
    assert judge(redline("b9.x", ["R1"]), "nope", c) == (None, None)


def test_redline_majority_and_trap():
    c = ctx(two=[run("creative", 3, hits=["R1"])] * 2 + [run("creative", 3)],
            one=[run("creative", 3, hits=["R1"])] + [run("creative", 3)] * 2)
    assert judge(redline("b9.x", ["R1"]), "two", c)[0] is True
    assert judge(redline("b9.x", ["R1"]), "one", c)[0] is False  # 1/3 只是疑似
    assert judge(redline("b9.x", ["R1"], hit=False), "one", c)[0] is True


def test_redline_clean_base():
    """真实素材基准本来就命中同一条红线时，注入用例不可判定。"""
    c = ctx(dirty=[run("creative", 3, hits=["R2"])] * 3, clean=[run("creative", 3)] * 3, v=[run("creative", 3, hits=["R2"])] * 3)
    assert judge(redline("b10.x", ["R2"], clean="clean"), "v", c)[0] is True
    assert judge(redline("b10.x", ["R2"], clean="dirty"), "v", c)[0] is None
    assert judge(redline("b10.x", ["R2"], clean="missing"), "v", c)[0] is None


def test_verdict():
    c = ctx(p=[run("creative", 5)] * 3, r=[run("creative", 3, hits=["R2"])] * 3)
    assert judge(verdict("b9.x", allow=["通过"]), "p", c)[0] is True
    assert judge(verdict("b9.x", deny=["通过"]), "r", c)[0] is True
    assert judge(verdict("b9.x", deny=["驳回", "驳回（命中红线）"]), "r", c)[0] is False


def test_mention_majority():
    r1 = run("creative", 3)
    r1["dimensions"][0]["evidence"] = "材料未提供分镜"
    c = ctx(a=[r1, r1, run("creative", 3)], b=[r1, run("creative", 3), run("creative", 3)])
    k = mention("b9.x", "dims:C1", "未提供")
    assert judge(k, "a", c)[0] is True and judge(k, "b", c)[0] is False


def test_locus_only_counts_runs_that_hit():
    hit_right = run("creative", 3, hits=["R1"])
    hit_right["redlines"][0]["evidence"] = "镜 3 出现危险驾驶"
    hit_wrong = run("creative", 3, hits=["R1"])
    hit_wrong["redlines"][0]["evidence"] = "第5镜有问题"
    c = ctx(a=[hit_right, hit_right, hit_wrong], b=[hit_wrong, run("creative", 3), run("creative", 3)], n=[run("creative", 3)] * 3)
    k = locus("b9.x", "redlines:R1", shot=3)
    assert judge(k, "a", c)[0] is True
    assert judge(k, "b", c)[0] is False  # 唯一命中的那次指错了镜号
    assert judge(k, "n", c)[0] is None   # 没命中：定位不可判定


def test_located_forms():
    assert located("第 3 镜危险", {"shot": 3}) and located("镜3：危险", {"shot": 3}) and not located("镜 30 秒", {"shot": 3})
    assert located("关键帧 @ 12.50s 出现字卡", {"t": [12.25, 12.75]}) and not located("15.0s", {"t": [12.25, 12.75]})
    assert located("06_产品主视觉KV 品牌名错", {"image": "06_产品主视觉KV.png"})
    assert located("主视觉上写成了远蓝", {"image": "12_产品主视觉KV.png"})
    assert not located("角色设定_侧面有问题", {"image": "12_产品主视觉KV.png"})
    assert located("台词「全网 第一」", {"quote": "全网第一"})


def test_times_ignore_aspect_clock_and_duration():
    assert times_in("关键帧 @ 3.50s、第 12 秒") == [3.5, 12.0]
    assert times_in("画幅 9:16，闹钟显示 03:00，时长 30.0s，平台要求 15 秒") == []


def test_order():
    c = ctx(a=[run("creative", 5)] * 3, b=[run("creative", 4)] * 3, c=[run("creative", 2)] * 3)
    assert judge(order("b9.x", ["C1"], ["a", "b", "c"]), "c", c)[0] is True
    assert judge(order("b9.x", ["C1"], ["b", "a", "c"]), "c", c)[0] is False  # 中间升了 1，超过容差
    assert judge(order("b9.x", ["C1"], ["a", "a"]), "a", c)[0] is False       # 首尾相等不算排对


def test_spearman():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 2, 2], [1, 2, 3, 4]) == pytest.approx(0.894, abs=1e-3)  # 并列取平均秩
    assert spearman([1, 2], [1, 2]) is None and spearman([1, 1, 1], [1, 2, 3]) is None


def test_metrics_rates_report_only_and_tiers():
    labs = [lab("v1", checks=[drop("b9.blind_drop", ["C1"], "base")]),
            lab("v2", checks=[drop("b9.blind_drop", ["C1"], "base"), mention("b9.noticed", "all", "灰", report=True)])]
    res = {"base": mkres("creative", [run("creative", 4)] * 3), "v1": mkres("creative", [run("creative", 2)] * 3),
           "v2": mkres("creative", [run("creative", 4)] * 3)}
    labels = {l["case_id"]: l for l in labs} | {"base": lab("base")}
    meta = {"e6": {"tiers": {"v1": "reject", "v2": "pass"}}}
    M, fails, _ = metrics(res, labs, meta, labels)
    assert M["b9.blind_drop"]["k"] == 1 and M["b9.blind_drop"]["n"] == 2 and M["b9.blind_drop"]["mean_delta"] == 1.0
    assert "b9.noticed" in M["_report_only"] and "b9.blind_drop" not in M["_report_only"]
    assert [f[0] for f in fails] == ["v2"]  # 只报告的 check 不进未通过列表
    # v1 总分 2 → 驳回（应驳回，对）；v2 总分 4 → 通过（应通过，对）
    assert M["e6.cross_tier_errors"]["value"] == 0 and M["e6.accuracy"]["rate"] == 1.0


def test_derived_monotone_and_scale_drop():
    c = ctx(a=[run("creative", 4)] * 3, b=[run("creative", 3)] * 3, d=[run("creative", 2)] * 3)
    M = {"b21.recall/text.5k": {"rate": 1.0}, "b21.recall/text.20k": {"rate": 0.9}, "b21.recall/text.60k": {"rate": 0.6}}
    meta = {"b12": {"series": {"s1": {"dims": ["C1"], "ids": ["a", "b", "d"]}, "s2": {"dims": ["C1"], "ids": ["b", "a", "d"]}}}}
    derived(M, c, meta, {})
    assert M["b12.monotone"]["k"] == 1 and M["b12.monotone"]["n"] == 2
    assert M["b21.scale_drop/text"]["value"] == pytest.approx(0.4)


# ---------------- 标签完整性（有标签时才跑） ----------------
LABELS = load_v2()
needs_labels = pytest.mark.skipif(not LABELS, reason="还没生成第二轮用例（cases_v2.py）")


@needs_labels
def test_labels_well_formed():
    ids = [l["case_id"] for l in LABELS]
    assert len(ids) == len(set(ids))
    for l in LABELS:
        for c in l["checks"]:
            assert c["key"].startswith(l["family"] + "."), (l["case_id"], c["key"])
            if c["t"] == "redline":
                assert set(c["ids"]) <= set(redline_ids(l["stage"])), l["case_id"]
            if c["t"] in ("delta", "corr", "order") and c["dims"] != "total":
                assert set(c["dims"]) <= set(dim_ids(l["stage"])), (l["case_id"], c["dims"])
        assert "通过" not in json.dumps(l["expect"], ensure_ascii=False)  # 第一轮 score 不应误算第二轮用例


@needs_labels
def test_labels_references_and_materials():
    from cases_v2 import check, load
    labels, meta = load()
    bad = check(labels, meta)
    assert not bad, bad[:10]


@needs_labels
def test_every_gated_family_has_a_threshold():
    from common import BENCH
    th = json.loads((BENCH / "thresholds.json").read_text(encoding="utf-8"))
    gated = {c["key"].split("/")[0] for l in LABELS for c in l["checks"] if not c.get("report")}
    covered = {k.split("/")[0] for k in th}
    assert gated <= covered, sorted(gated - covered)


def test_meta_series_exist_when_labels_exist():
    p = V2 / "meta.json"
    if not p.exists():
        pytest.skip("没有 meta.json")
    meta = json.loads(p.read_text(encoding="utf-8"))
    for fam in ("b12", "b21"):
        if fam in meta:
            assert meta[fam]["series"], fam


def test_gate_state():
    from common import gate_state, rate
    t = {"field": "rate", "min": 0.85}
    assert gate_state(rate([True] * 5 + [False]), t)[0] == "small"
    assert gate_state(rate([True] * 90 + [False] * 10), t)[0] == "pass"
    assert gate_state(rate([True] * 16 + [False] * 4), t)[0] == "unsure"   # 0.80，区间上限 > 0.85
    assert gate_state(rate([True] * 60 + [False] * 40), t)[0] == "fail"
    assert gate_state(rate([True] * 2 + [False] * 34), {"field": "rate", "max": 0.05})[0] == "unsure"  # b8 第一轮 2/36
    assert gate_state({"value": 0.3}, {"field": "value", "min": 0.4})[0] == "fail"
