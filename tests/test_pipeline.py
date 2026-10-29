"""evaluate / 网站 worker / .env：把各部件串起来，用桩服务器代替模型。"""
import json
import os
import sys
from pathlib import Path

import pytest

import media
import video_review as vr
from bugs import bug
from conftest import ROOT, completion, make_run

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def test_evaluate_creative_end_to_end(rubric, stub_llm, tmp_path):
    stub_llm.push(completion(make_run(rubric, "creative", [3] * 8), {"prompt_tokens": 100, "completion_tokens": 10}))
    stub_llm.push(completion(make_run(rubric, "creative", [5] * 8), {"prompt_tokens": 100, "completion_tokens": 20}))
    stub_llm.push(completion(make_run(rubric, "creative", [4] * 8), {"prompt_tokens": 100, "completion_tokens": 30}))
    brief = write(tmp_path / "brief.md", "brief")
    prop = write(tmp_path / "proposal.md", "提案")
    ev = vr.evaluate("creative", [prop], [brief], None, runs=3, key="sk-x")
    assert len(stub_llm.requests) == 3
    assert ev["usage"] == {"prompt_tokens": 300, "completion_tokens": 60}
    assert ev["result"]["total"] == 4.0 and ev["result"]["verdict"] == "通过" and ev["tech"] is None
    assert sorted(d["dimensions"][0]["score"] for d in ev["raw_runs"]) == [3, 4, 5]
    bodies = [r["body"] for r in stub_llm.requests]
    assert all(b == bodies[0] for b in bodies), "三次采样必须发同一份提示词"
    sys_prompt, user = bodies[0]["messages"][0]["content"], bodies[0]["messages"][1]["content"]
    assert sys_prompt == vr.build_system_prompt("creative", rubric)
    assert "提案" in user[-1]["text"] and "brief" in user[2]["text"]


def test_evaluate_video_sends_frames(rubric, stub_llm, tmp_path):
    stub_llm.default = completion(make_run(rubric, "video", [4] * len(rubric["stages"]["video"]["dimensions"])))
    ev = vr.evaluate("video", [media.video(dur=5, audio=0.25)], runs=1, frames=2, key="sk-x")
    user = stub_llm.requests[0]["body"]["messages"][1]["content"]
    assert sum(c["type"] == "image_url" for c in user) == 9
    assert ev["tech"]["分辨率"] == "320x180"


def test_evaluate_multiple_videos_sends_each_tech_block(rubric, stub_llm):
    # 送给模型的内容里两个视频的参数都在（对照用例，保证 B35 只针对返回值/报告）
    stub_llm.default = completion(make_run(rubric, "video", [4] * len(rubric["stages"]["video"]["dimensions"])))
    vr.evaluate("video", [media.video(320, 180, dur=4), media.video(180, 320, dur=4)], runs=1, frames=1, key="sk-x")
    text = "".join(c.get("text", "") for c in stub_llm.requests[0]["body"]["messages"][1]["content"])
    assert "320x180" in text and "180x320" in text


def test_evaluate_multiple_videos_keeps_all_tech(rubric, stub_llm):
    stub_llm.default = completion(make_run(rubric, "video", [4] * len(rubric["stages"]["video"]["dimensions"])))
    ev = vr.evaluate("video", [media.video(320, 180, dur=4), media.video(180, 320, dur=4)], runs=1, frames=1, key="sk-x")
    dumped = json.dumps(ev["tech"], ensure_ascii=False)
    assert "320x180" in dumped and "180x320" in dumped


def test_evaluate_custom_rubric_path(rubric, stub_llm, tmp_path):
    rb = json.loads(json.dumps(rubric))
    rb["verdict_rules"]["pass"]["min_score"] = 4.5
    path = write(tmp_path / "r.json", json.dumps(rb, ensure_ascii=False))
    stub_llm.default = completion(make_run(rubric, "creative", [4] * 8))
    ev = vr.evaluate("creative", [write(tmp_path / "a.md", "x")], runs=1, rubric_path=path, key="sk-x")
    assert ev["result"]["verdict"] == "修改后通过"


def test_evaluate_model_failure_raises(rubric, stub_llm, tmp_path):
    stub_llm.default = completion("不是 JSON")
    with pytest.raises(RuntimeError):
        vr.evaluate("creative", [write(tmp_path / "a.md", "x")], runs=2, key="sk-x")


def test_evaluate_incomplete_model_output_is_error_not_crash(rubric, stub_llm, tmp_path):
    stub_llm.default = completion({"summary": "缺字段"})
    try:
        vr.evaluate("creative", [write(tmp_path / "a.md", "x")], runs=1, key="sk-x")
    except RuntimeError:
        return
    pytest.fail("应重试或报 RuntimeError")


# ---------- CLI ----------

def test_cli_writes_json_and_markdown(rubric, stub_llm, tmp_path, monkeypatch):
    stub_llm.default = completion(make_run(rubric, "creative", [4] * 8))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["video_review.py", "creative", str(write(tmp_path / "提案.md", "x")),
                                      "--runs", "2", "--out", str(out)])
    vr.main()
    js, = out.glob("creative_提案_*.json")
    md, = out.glob("creative_提案_*.md")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["result"]["verdict"] == "通过" and len(data["raw_runs"]) == 2
    assert "× 2 次采样" in md.read_text(encoding="utf-8") and len(stub_llm.requests) == 2


@pytest.mark.parametrize("bad", [["--runs", "0"], ["--runs", "-1"], ["--frames", "-1"]])
def test_cli_rejects_nonpositive_counts(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setattr(sys, "argv", ["video_review.py", "creative", str(write(tmp_path / "a.md", "x")), *bad])
    with pytest.raises(SystemExit) as e:
        vr.main()
    assert e.value.code == 2  # argparse 参数错误


# ---------- 基准运行器 ----------

def test_run_benchmark_runs_and_resumes(rubric, stub_llm, tmp_path, monkeypatch):
    import run_benchmark as rb
    monkeypatch.setattr(rb, "HERE", tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    write(tmp_path / "a.md", "x")
    labels = [{"case_id": f"c{i}", "stage": "creative", "inputs": {"files": ["a.md"]}} for i in range(3)]
    args = SimpleArgs(name="t", runs=1, model="m", effort="high", workers=2)
    stub_llm.default = completion(make_run(rubric, "creative", [4] * 8))
    rb.run_all(labels, args)
    assert sorted(p.name for p in (tmp_path / "results" / "t").iterdir()) == ["c0.json", "c1.json", "c2.json"]
    rb.run_all(labels, args)
    assert len(stub_llm.requests) == 3, "已完成的用例应跳过"


class SimpleArgs:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ---------- 网站 worker ----------

def run_worker(job_dir, monkeypatch):
    sys.path.insert(0, str(ROOT / "review-site" / "worker"))
    import run_job
    monkeypatch.setattr(run_job, "video_review", vr)
    monkeypatch.setattr(sys, "argv", ["run_job.py", str(job_dir)])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    run_job.main()
    return json.loads((job_dir / "status.json").read_text(encoding="utf-8"))


def make_job(tmp_path, **job):
    d = tmp_path / "job"
    d.mkdir()
    f = write(tmp_path / "提案.md", "创意提案")
    write(d / "job.json", json.dumps({"stage": "creative", "files": [str(f)], "runs": 2, **job}, ensure_ascii=False))
    write(d / "status.json", json.dumps({"state": "running", "created": 1, "started": 2}))
    return d


def test_worker_success(rubric, stub_llm, tmp_path, monkeypatch):
    stub_llm.default = completion(make_run(rubric, "creative", [4] * 8))
    d = make_job(tmp_path, platform_hint="视频号 9:16")
    st = run_worker(d, monkeypatch)
    assert st["state"] == "done" and st["created"] == 1 and st["started"] == 2 and st["finished"] > 0
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    assert res["result"]["verdict"] == "通过" and len(res["raw_runs"]) == 2
    assert (d / "report.md").read_text(encoding="utf-8").startswith("# G1 创意评审报告")
    assert len(stub_llm.requests) == 2


def test_worker_model_error_sets_error_state(stub_llm, tmp_path, monkeypatch):
    stub_llm.push({"error": {"message": "Insufficient Balance"}}, 402)
    stub_llm.default = {"error": "x"}
    # 只采样 1 次：多次采样时哪个线程先拿到 402 不确定，抛出的错误会随时序变化
    st = run_worker(make_job(tmp_path, runs=1), monkeypatch)
    assert st["state"] == "error" and "鉴权或余额" in st["error"] and len(st["error"]) <= 500
    assert not (tmp_path / "job" / "result.json").exists()


# ---------- .env ----------

@pytest.fixture
def env_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "HERE", tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    return tmp_path


def test_env_file_plain(env_dir):
    write(env_dir / ".env", "OTHER=1\nDEEPSEEK_API_KEY=sk-abc\n")
    assert vr.load_api_key() == "sk-abc"


def test_env_var_wins(env_dir, monkeypatch):
    write(env_dir / ".env", "DEEPSEEK_API_KEY=sk-file\n")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    assert vr.load_api_key() == "sk-env"


def test_missing_key_exits(env_dir):
    with pytest.raises(SystemExit):
        vr.load_api_key()


@pytest.mark.parametrize("line", ['DEEPSEEK_API_KEY="sk-abc"', "DEEPSEEK_API_KEY='sk-abc'", "  DEEPSEEK_API_KEY=sk-abc",
                                  "export DEEPSEEK_API_KEY=sk-abc", "﻿DEEPSEEK_API_KEY=sk-abc"])
def test_env_file_variants(env_dir, line):
    write(env_dir / ".env", line + "\n")
    assert vr.load_api_key() == "sk-abc"
