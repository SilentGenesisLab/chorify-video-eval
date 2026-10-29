"""B 层门槛：读一次真实评测的 metrics.json，按 thresholds.json 逐条核对。

没设 VR_BENCH_METRICS 时整体跳过（平时跑 A 层不受影响）：
  $env:VR_BENCH_METRICS = "tests/bench/results/b1/r1/metrics.json"
  .venv/Scripts/python -X utf8 -m pytest tests/bench/test_bench_gates.py -v
"""
import json
import os
from pathlib import Path

import pytest

from common import BENCH, MIN_N, gate_state

TH = {k: v if isinstance(v, list) else [v]
      for k, v in json.loads((BENCH / "thresholds.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
PATH = os.environ.get("VR_BENCH_METRICS")
M = json.loads(Path(PATH).read_text(encoding="utf-8")) if PATH else {}
pytestmark = pytest.mark.skipif(not PATH, reason="未设置 VR_BENCH_METRICS")


def cases():
    """展开 "x/*" 到 metrics 里实际存在的每个关卡；没有匹配时保留原键，测试里跳过。"""
    for key, checks in TH.items():
        keys = [k for k in M if k.startswith(key[:-1])] if key.endswith("/*") else [key]
        for k in keys or [key]:
            for i, c in enumerate(checks):
                yield pytest.param(k, c, id=f"{k}.{c['field']}" if len(checks) > 1 else k)


def value(v, field):
    if field == "len":
        return len(v)
    if field == "value" and not isinstance(v, dict):
        return v
    if field == "not_ok":
        return sum(1 for s in v.values() if not s["ok"]) if v else None
    if field == "max_flip":
        rs = [g["verdict_flip"]["rate"] for g in v.values() if g["verdict_flip"]["rate"] is not None]
        return max(rs) if rs else None
    return v.get(field)


def test_value_extraction():
    """门槛取值本身的语义（随 VR_BENCH_METRICS 一起跑）。"""
    assert value({"a": {"ok": True}, "b": {"ok": False}}, "not_ok") == 1
    assert value({}, "not_ok") is None
    assert value({"g": {"verdict_flip": {"rate": 0.1}}, "h": {"verdict_flip": {"rate": 0.3}}}, "max_flip") == 0.3
    assert value(["x"], "len") == 1 and value(0, "value") == 0



@pytest.mark.parametrize("key,t", list(cases()))
def test_gate(key, t):
    if key not in M:
        pytest.skip("本批结果没有这项指标")
    if t["field"] == "rate":  # 比率按区间判：样本太少、区间跨过门槛都不下结论
        st, x = gate_state(M[key], t)
        if st is None:
            pytest.skip("样本为空")
        if st == "small":
            pytest.skip(f"n={M[key]['n']} < {MIN_N}，只报告")
        if st == "unsure":
            pytest.skip(f"{key} = {x:.3f}，95% 区间 {M[key]['lo']:.3f}–{M[key]['hi']:.3f} 跨过门槛，样本不足以下结论")
        assert st == "pass", f"{key}.rate = {x:.3f}（95% 区间 {M[key]['lo']:.3f}–{M[key]['hi']:.3f}）不满足 {t}"
        return
    x = value(M[key], t["field"])
    if x is None:
        pytest.skip("样本为空（如 runs=1 没有极差、没有探针序列）")
    if "min" in t:
        assert x >= t["min"], f"{key}.{t['field']} = {x} < {t['min']}"
    if "max" in t:
        assert x <= t["max"], f"{key}.{t['field']} = {x} > {t['max']}"
