"""端到端评测打分：评审器的结论和 tvcagent 审核门上的人工决定对得上吗。

python tests/e2e/score_e2e.py [--cases %TEMP%/vr_e2e/cases.json] [--out report.md]

三类对照（都没有「标准答案」，只有人工审核记录）：
1. 终版（final）：人工最终放行的版本。评审器判「驳回（命中红线）」的逐条列出，人工复核是误报还是人漏了。
2. 负例对（neg vs pos/final）：同一条片子 / 同一组关键帧，只把人工驳回过的那几镜换回驳回版。
   - 区分度：负例总分 < 正例总分，或负例多命中红线 / 结论更差
   - 定位：评审器的 issues / evidence 里提到被换掉的镜号或时间段
3. 流水线全链：同一个 roll 的四道关卡结论放在一起看。
"""
import argparse
import json
import pathlib
import re
import tempfile

DEFAULT = pathlib.Path(tempfile.gettempdir()) / "vr_e2e" / "cases.json"
RANK = {"通过": 3, "修改后通过": 2, "驳回": 1, "驳回（命中红线）": 0, "无法判定（评审输出不完整）": None}


def load(cases_path):
    cases = json.loads(pathlib.Path(cases_path).read_text(encoding="utf-8"))
    res = {}
    for c in cases:
        p = pathlib.Path(cases_path).parent / "results" / f"{c['case_id']}.json"
        if p.exists():
            res[c["case_id"]] = json.loads(p.read_text(encoding="utf-8"))["job"]["result"]
    return cases, res


def hits(r):
    return sorted(x["id"] for x in r.get("redlines", []) if x.get("status") == "命中")


def suspects(r):
    return sorted(x["id"] for x in r.get("redlines", []) if str(x.get("status", "")).startswith("疑似"))


def text_of(r):
    parts = [r.get("summary", "")] + list(r.get("top_fixes") or [])
    for d in r.get("dimensions", []):
        parts += [d.get("evidence", "")] + list(d.get("issues") or [])
    parts += [x.get("evidence", "") for x in r.get("redlines", []) if x.get("status") != "未命中"]
    return "\n".join(map(str, parts))


SEC = re.compile(r"(\d+(?:\.\d+)?)\s*(?:s|秒)")


def located(r, case):
    t = text_of(r)
    for s in case.get("shots", []):
        n = s[1:] if s.startswith("S") else s
        if re.search(rf"(镜\s*{n}(?!\d)|S{n}(?!\d)|镜头\s*{n}(?!\d)|第\s*{n}\s*镜)", t):
            return True
    for a, b in (case.get("windows") or {}).values():
        if any(a - 1 <= float(x) <= b + 1 for x in SEC.findall(t)):
            return True
    return False


def dims(r):
    return {d["id"]: d.get("score") for d in r.get("dimensions", [])}


def fmt(r):
    if not r:
        return "—"
    h = hits(r)
    return f"{r.get('verdict')} {r.get('total')}" + (f" {'/'.join(h)}" if h else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(DEFAULT))
    ap.add_argument("--out")
    a = ap.parse_args()
    cases, res = load(a.cases)
    by_id = {c["case_id"]: c for c in cases}
    L = [f"结果 {len(res)}/{len(cases)} 例", ""]

    # 1. 全链
    rolls = sorted({c["roll"] for c in cases})
    L += ["## 全链结论（终版）", "", "| roll | 创意 | 分镜 | 资产（关键帧） | 成片 |", "|---|---|---|---|---|"]
    for rl in rolls:
        row = [fmt(res.get(f"{rl}__{s}")) for s in ("creative", "storyboard", "asset", "video")]
        L.append(f"| {rl} | " + " | ".join(row) + " |")

    # 2. 终版命中红线
    L += ["", "## 终版被判红线（人工已放行）", "", "| 用例 | 红线 | 评审器证据 |", "|---|---|---|"]
    n_final = n_red = 0
    for c in cases:
        r = res.get(c["case_id"])
        if c["kind"] != "final" or not r:
            continue
        n_final += 1
        for x in r.get("redlines", []):
            if x.get("status") == "命中":
                n_red += 1
                L.append(f"| `{c['case_id']}` | {x['id']} {x['text'][:20]} | {str(x.get('evidence', ''))[:160].replace('|', '／')} |")
    L.insert(2, f"- 终版 {n_final} 例，判红线 {n_red} 条")

    # 3. 负例对
    L += ["", "## 人工驳回版 vs 放行版", "",
          "| 负例 | 换掉的镜 | 人工驳回理由 | 放行版 | 驳回版 | 分差 | 区分 | 定位 |", "|---|---|---|---|---|---|---|---|"]
    sep = loc = n = 0
    for c in cases:
        if c["kind"] != "neg":
            continue
        rn, rp = res.get(c["case_id"]), res.get(c["pair"])
        if not rn or not rp:
            continue
        n += 1
        tn, tp = rn.get("total"), rp.get("total")
        worse_verdict = (RANK.get(rn["verdict"]) is not None and RANK.get(rp["verdict"]) is not None
                         and RANK[rn["verdict"]] < RANK[rp["verdict"]])
        more_hits = set(hits(rn)) - set(hits(rp))
        ok = (tn is not None and tp is not None and tn < tp - 0.05) or worse_verdict or bool(more_hits)
        lc = located(rn, c)
        sep += ok
        loc += lc
        L.append(f"| `{c['case_id']}` | {','.join(c['shots'])} | {c['human_reject'][:60].replace('|', '／')}… | {fmt(rp)} | {fmt(rn)} | "
                 f"{(tn - tp):+.2f} | {'是' if ok else '否'} | {'是' if lc else '否'} |" if tn is not None and tp is not None else
                 f"| `{c['case_id']}` | — | — | {fmt(rp)} | {fmt(rn)} | — | — | — |")
    L.insert(3, f"- 人工驳回版 {n} 例：评审器判得比放行版差 {sep} 例，指出被换掉的镜 {loc} 例")

    # 4. 单维度变化（负例）
    L += ["", "## 负例里降得最多的维度", ""]
    for c in cases:
        rn, rp = res.get(c["case_id"]), res.get(c.get("pair"))
        if c["kind"] != "neg" or not rn or not rp:
            continue
        dn, dp = dims(rn), dims(rp)
        ch = sorted(((k, (dn.get(k) or 0) - (dp.get(k) or 0)) for k in dn if dn.get(k) is not None and dp.get(k) is not None),
                    key=lambda x: x[1])[:3]
        L.append(f"- `{c['case_id']}`：" + "，".join(f"{k} {d:+.2f}" for k, d in ch))
    text = "\n".join(L) + "\n"
    if a.out:
        pathlib.Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
