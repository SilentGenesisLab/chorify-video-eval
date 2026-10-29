"""render_markdown：报告内容与表格结构。"""
from types import SimpleNamespace

import pytest

import video_review as vr
from bugs import bug
from conftest import make_run

ARGS = SimpleNamespace(files=["/x/成片.mp4", "subs.srt"], model="deepseek-flash", runs=3)
USAGE = {"prompt_tokens": 11, "completion_tokens": 22}


def result(rubric, stage="video", **over):
    n = len(rubric["stages"][stage]["dimensions"])
    r = vr.aggregate(stage, rubric, [make_run(rubric, stage, [4] * n)] * 3)
    r.update(over)
    return r


def table_rows(md, header):
    lines = md.splitlines()
    i = lines.index(header)
    rows = []
    for line in lines[i:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return rows


def test_header_and_sections(rubric):
    md = vr.render_markdown(result(rubric), None, ARGS, USAGE)
    assert md.startswith("# G4 成片评审报告\n")
    assert "- 评审对象：成片.mp4, subs.srt" in md
    assert "- 模型：deepseek-flash × 3 次采样 · " in md
    assert "- **结论：通过** · 加权总分 **4.0** / 5 · 最低维度 4" in md
    assert "## 技术参数" not in md
    assert "> 总评" in md and "1. 改法 1" in md and "- 亮点" in md
    assert md.endswith("Token 用量：{'prompt_tokens': 11, 'completion_tokens': 22}")


def test_human_review_line(rubric):
    r = result(rubric, needs_human_review=["V1", "R2"], review_reasons={"V1": "多次采样分歧 2 分"})
    md = vr.render_markdown(r, None, ARGS, USAGE)
    assert "- ⚠ 需人工复核：V1（多次采样分歧 2 分）；R2" in md


def test_no_human_review_line_when_empty(rubric):
    md = vr.render_markdown(result(rubric, needs_human_review=[]), None, ARGS, USAGE)
    assert "需人工复核" not in md


def test_multi_video_tech_tables(rubric):
    tech = {"a.mp4": {"分辨率": "320x180"}, "b.mp4": {"分辨率": "180x320"}}
    md = vr.render_markdown(result(rubric), tech, ARGS, USAGE)
    assert "## 技术参数（程序测量）：a.mp4" in md and "| 分辨率 | 180x320 |" in md


def test_tables_have_one_row_per_item(rubric):
    md = vr.render_markdown(result(rubric), None, ARGS, USAGE)
    s = rubric["stages"]["video"]
    assert len(table_rows(md, "| ID | 红线 | 结果 | 命中次数 | 证据/疑点 |")) == 2 + len(s["redlines"])
    dims = table_rows(md, "| ID | 维度 | 权重 | 均分 | 各次得分 |")
    assert len(dims) == 2 + len(s["dimensions"]) and dims[2] == "| V1 | 开场吸引力 | 15% | 4 | [4, 4, 4] |"
    assert md.count("### V") == len(s["dimensions"])


def test_tech_table(rubric):
    tech = {"分辨率": "320x180", "黑帧区间": ["2s–2.5s", "5s–6s"], "冻结帧起点": [], "音频": "无音轨"}
    md = vr.render_markdown(result(rubric), tech, ARGS, USAGE)
    assert "| 分辨率 | 320x180 |" in md and "| 黑帧区间 | 2s–2.5s, 5s–6s |" in md and "| 音频 | 无音轨 |" in md


@pytest.mark.parametrize("value", [0.0, 0])
def test_zero_tech_value_shown(rubric, value):
    md = vr.render_markdown(result(rubric), {"响度范围(LU)": value}, ARGS, USAGE)
    assert f"| 响度范围(LU) | {value} |" in md


def test_empty_list_tech_value(rubric):
    md = vr.render_markdown(result(rubric), {"冻结帧起点": []}, ARGS, USAGE)
    assert "| 冻结帧起点 | 无 |" in md or "| 冻结帧起点 |  |" in md


def test_table_cells_escaped(rubric):
    r = result(rubric)
    r["redlines"][0]["evidence"] = "第 1 行\n第 2 行 | 带竖线"
    md = vr.render_markdown(r, None, ARGS, USAGE)
    rows = table_rows(md, "| ID | 红线 | 结果 | 命中次数 | 证据/疑点 |")
    assert len(rows) == 2 + len(rubric["stages"]["video"]["redlines"]) and all(row.count("|") - row.count("\\|") == 6 for row in rows)


def test_weight_percent_rounded(rubric):
    r = result(rubric)
    r["dimensions"][0]["weight"] = 0.29
    assert "| V1 | 开场吸引力 | 29% |" in vr.render_markdown(r, None, ARGS, USAGE)
