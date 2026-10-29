"""rubrics.json 自身的合法性、与《视频评审框架.md》的一致性、基准数据集标签的完整性与覆盖。"""
import json
import re
from collections import defaultdict
from fractions import Fraction

import pytest

from bugs import bug
from conftest import ROOT

STAGES = {"creative": ("C", "1. G1"), "storyboard": ("S", "2. G2"), "asset": ("A", "3. G3"), "video": ("V", "4. G4")}
DOC = (ROOT / "视频评审框架.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def labels():
    return [json.loads(x) for x in (ROOT / "benchmark" / "dataset" / "labels.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


# ---------- rubrics.json ----------

@pytest.mark.parametrize("stage", STAGES)
def test_weights_sum_to_one(rubric, stage):
    assert sum(Fraction(str(d["weight"])) for d in rubric["stages"][stage]["dimensions"]) == 1


@pytest.mark.parametrize("stage", STAGES)
def test_dimension_ids_sequential(rubric, stage):
    ids = [d["id"] for d in rubric["stages"][stage]["dimensions"]]
    assert ids == [f"{STAGES[stage][0]}{i}" for i in range(1, len(ids) + 1)]


@pytest.mark.parametrize("stage", STAGES)
def test_fields_present(rubric, stage):
    s = rubric["stages"][stage]
    assert s["name"] and s["input_hint"] and s["redlines"]
    for d in s["dimensions"]:
        assert all(str(d[k]).strip() for k in ("name", "criteria", "anchor_5", "anchor_2")) and 0 < d["weight"] < 1


def test_scale_and_rules(rubric):
    assert sorted(rubric["scale"]) == ["1", "2", "3", "4", "5"]
    p, r = rubric["verdict_rules"]["pass"], rubric["verdict_rules"]["revise"]
    assert p["min_score"] >= r["min_score"] and p["min_dimension"] >= r["min_dimension"]


# ---------- 与框架文档一致 ----------

def doc_section(prefix):
    start = DOC.index(f"## {prefix}")
    nxt = DOC.find("\n## ", start + 3)
    return DOC[start:nxt if nxt > 0 else None]


@pytest.mark.parametrize("stage", STAGES)
def test_doc_dimension_table_matches(rubric, stage):
    sec = doc_section(STAGES[stage][1])
    norm = lambda s: re.sub(r"\s+", "", s)  # 只忽略空白差异（如 "A / B" 与 "A/B"）
    rows = [(i, norm(n), w) for i, n, w in re.findall(r"^\| ([CSAV]\d) \| ([^|]+?) \| (\d+)% \|", sec, re.M)]
    want = [(d["id"], norm(d["name"]), str(round(d["weight"] * 100))) for d in rubric["stages"][stage]["dimensions"]]
    assert rows == want


def doc_redline_count(stage):
    sec = doc_section(STAGES[stage][1])
    if stage == "video":
        sub = sec[sec.index("### 4.3"):]
        return len(re.findall(r"^- \*\*", sub, re.M))
    line = re.search(r"\*\*红线\*\*：(.+)", sec)[1]
    return len([x for x in re.split("[；;]", line.rstrip("。")) if x.strip()])


@pytest.mark.parametrize("stage", [
    "creative", "asset",
    "storyboard",
    "video",
])
def test_doc_redline_count_matches(rubric, stage):
    assert doc_redline_count(stage) == len(rubric["stages"][stage]["redlines"])


def test_doc_pass_rule_matches(rubric):
    p = rubric["verdict_rules"]["pass"]
    assert f"加权总分 ≥ {p['min_score']} 且没有任何维度 < {p['min_dimension']} → **通过**" in DOC


def test_doc_revise_rule_matches(rubric):
    # 文档写"没有任何维度 = 1"，rubrics 是 min_dimension ≥ 2：均分 1.67 时前者放行、后者驳回
    r = rubric["verdict_rules"]["revise"]
    assert f"加权总分 ≥ {r['min_score']} 且没有任何维度 < {r['min_dimension']} → **修改后通过**" in DOC


# ---------- 基准数据集 ----------

def test_label_integrity(rubric, labels):
    ids = {l["case_id"] for l in labels}
    assert len(ids) == len(labels)
    for l in labels:
        s = rubric["stages"][l["stage"]]
        dims = {d["id"] for d in s["dimensions"]}
        reds = {f"R{i + 1}" for i in range(len(s["redlines"]))}
        e = l["expect"]
        assert set(e["redlines"]) <= reds and set(e["target"]) <= dims, l["case_id"]
        assert e["no_redline"] == (not e["redlines"]), l["case_id"]
        assert l["kind"] in ("base", "redline", "quality", "invariance") and l["split"] in ("dev", "test")
        assert (l["kind"] == "base") == (l["base_case_id"] is None), l["case_id"]
        if l["base_case_id"]:
            assert l["base_case_id"] in ids, l["case_id"]
        if l["kind"] == "redline":
            assert e["redlines"], l["case_id"]
        for f in l["inputs"]["files"] + l["inputs"].get("context", []):
            assert not f.startswith(("/", "..")) and ".." not in f, l["case_id"]


def test_text_inputs_present(labels):
    missing = [f for l in labels for f in l["inputs"]["files"] + l["inputs"].get("context", [])
               if f.endswith((".md", ".srt", ".txt")) and not (ROOT / "benchmark" / f).exists()]
    assert missing == []


@pytest.mark.parametrize("stage", ["creative", "storyboard", "asset", pytest.param("video", marks=bug("B41"))])
def test_every_stage_has_invariance_variants(labels, stage):
    assert any(l["stage"] == stage and l["kind"] == "invariance" for l in labels)


@pytest.mark.parametrize("stage", [
    "storyboard",
    pytest.param("creative", marks=bug("B28")),
    pytest.param("asset", marks=bug("B28")),
    pytest.param("video", marks=bug("B28")),
])
def test_every_redline_and_dimension_has_a_case(rubric, labels, stage):
    cov = defaultdict(set)
    for l in labels:
        cov[l["stage"]] |= set(l["expect"]["redlines"]) | set(l["expect"]["target"])
    s = rubric["stages"][stage]
    need = [d["id"] for d in s["dimensions"]] + [f"R{i + 1}" for i in range(len(s["redlines"]))]
    assert [x for x in need if x not in cov[stage]] == []
