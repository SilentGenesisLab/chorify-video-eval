"""变异测试：往 video_review.py 的副本里逐个注入典型错误，确认测试集能发现（"杀死"）每一个。

存活的变异体 = 测试集的盲区。用法：.venv/Scripts/python -X utf8 tests/mutate.py [-k 关键字]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "video_review.py").read_text(encoding="utf-8")

# (名称, 原文, 替换, 只跑哪些测试文件)
MUTANTS = [
    ("通过阈值 >= 改成 >", 'total >= rules["pass"]["min_score"]', 'total > rules["pass"]["min_score"]', "aggregate"),
    ("最低维度阈值 >= 改成 >", 'min_dim >= rules["pass"]["min_dimension"]', 'min_dim > rules["pass"]["min_dimension"]', "aggregate"),
    ("修改后通过阈值放宽", 'total >= rules["revise"]["min_score"]', 'total >= rules["revise"]["min_score"] - 0.5', "aggregate"),
    ("红线多数票改成 >=", "n_hit * 2 > len(runs)", "n_hit * 2 >= len(runs)", "aggregate"),
    ("红线疑似不转人审", 'flag(rid, f"只有 {n_hit}/{len(runs)} 次采样判命中")', "pass", "aggregate"),
    ("分歧阈值 2 改 3", 'dims[-1]["spread"] >= 2', 'dims[-1]["spread"] >= 3', "aggregate"),
    ("总分不加权", 'sum(d["mean"] * d["weight"] for d in scored) / sum(d["weight"] for d in dims)',
     'sum(d["mean"] for d in scored) / len(scored)', "aggregate"),
    ("缺失维度重新归一", 'sum(d["mean"] * d["weight"] for d in scored) / sum(d["weight"] for d in dims)',
     'sum(d["mean"] * d["weight"] for d in scored) / sum(d["weight"] for d in scored)', "aggregate"),
    ("缺维度照常判定", "elif not complete:", "elif False:", "aggregate"),
    ("红线 hit 只认 True", 'return v.strip().lower() in ("true", "1", "yes", "是", "命中")', "return False", "aggregate"),
    ("越界分照常计入", "and 1 <= v <= 5", "", "aggregate"),
    ("同一采样重复红线重复计票", 'sum(1 for xs in per_run if any(parse_hit(x.get("hit")) for x in xs))',
     'sum(1 for xs in per_run for x in xs if parse_hit(x.get("hit")))', "aggregate"),
    ("V3/V4 不再强制人审", 'ALWAYS_HUMAN = {"video": ("V3", "V4")}', "ALWAYS_HUMAN = {}", "aggregate"),
    ("驳回不转复核", 'flag(REJECT_REVIEW, "机审驳回，需法务 / 品牌复核")', "pass", "aggregate"),
    ("均分改中位数", "statistics.mean(scores)", "statistics.median(scores)", "aggregate"),
    ("红线命中不驳回", 'verdict = "驳回（命中红线）"', 'verdict = "通过"', "aggregate"),
    ("最低维度取 max", 'min((d["mean"] for d in scored), default=None)', 'max((d["mean"] for d in scored), default=None)', "aggregate"),
    ("鉴权错误也重试", "e.code in (401, 402)", "e.code in (403,)", "call_model"),
    ("重试次数少 1", "while attempt < retries:", "while attempt < retries - 1:", "call_model"),
    ("缺字段的输出不重试", 'isinstance(obj.get("dimensions"), list) and isinstance(obj.get("redlines"), list)', "True", "call_model"),
    ("响应阶段断线不重试", "http.client.HTTPException, ConnectionError, TimeoutError, ", "", "call_model"),
    ("不剥离 JSON 前的文字", r'for m in re.finditer(r"\{", text):', r'for m in re.finditer(r"\A", text):', "call_model"),
    ("丢掉 reasoning_effort", 'body["reasoning_effort"] = effort', "pass", "call_model"),
    ("温度改 0.7", '"temperature": 0.2', '"temperature": 0.7', "call_model"),
    ("黑帧阈值改 0.5 秒", "blackdetect=d=0.2", "blackdetect=d=0.5", "probe"),
    ("冻结阈值改 2 秒", "freezedetect=n=0.003:d=1.0", "freezedetect=n=0.003:d=2.0", "probe"),
    ("横竖屏判断反了", "'竖屏' if h > w", "'竖屏' if h < w", "probe"),
    ("时长少算分钟", "int(m[2]) * 60", "int(m[2])", "probe"),
    ("响度读成 LRA", r'I:\s+(-?[\d.]+) LUFS', r'LRA:\s+(-?[\d.]+) LU', "probe"),
    ("钩子帧间隔 0.5 改 1", "times = [t / 2 for t in range(0, 6) if t / 2 < duration]",
     "times = [t for t in range(0, 3) if t < duration]", "frames"),
    ("去掉尾帧", "times.append(tail)  # 尾帧（CTA）", "pass", "frames"),
    ("缩放上限 768 改 512", """"-frames:v", "1", "-vf", "scale='min(768,iw)'""", """"-frames:v", "1", "-vf", "scale='min(512,iw)'""", "frames"),
    ("均匀抽帧不取中点", "round(3 + step * (i + 0.5), 2)", "round(3 + step * i, 2)", "frames"),
    ("红线编号从 R0 开始", r'redlines = "\n".join(f"- R{i + 1}：{r}"', r'redlines = "\n".join(f"- R{i}：{r}"', "prompt"),
    ("提示词漏掉 2 分锚点", "f\"    5 分样子：{d['anchor_5']}；2 分样子：{d['anchor_2']}\"\n        for d in s[\"dimensions\"])",
     "f\"    5 分样子：{d['anchor_5']}；2 分样子：\"\n        for d in s[\"dimensions\"])", "prompt"),
    ("材料可伪造文件边界", 're.sub(r"^=====", "＝＝＝＝＝", read_text_file(path), flags=re.M)', "read_text_file(path)", "prompt"),
    ("参考材料放到最后", 'for c in context or []:', 'for c in []:', "prompt"),
    ("字幕不送", "if transcript:", "if False:", "prompt"),
    ("报告不显示人审", 'if result["needs_human_review"]:', "if False:", "report"),
    ("报告漏掉红线表", 'for r in result["redlines"]]', 'for r in result["redlines"][1:]]', "report"),
    ("采样只调一次", "calls = [(r, None, build_system_prompt(stage, rubric)) for r in range(runs)]",
     "calls = [(r, None, build_system_prompt(stage, rubric)) for r in range(1)]", "pipeline"),
    ("usage 只算第一次", 'sum(o[1].get(k, 0) for o in outs)', 'outs[0][1].get(k, 0)', "pipeline"),
    (".env 优先于环境变量", "if os.environ.get(name):\n        return os.environ[name]", "if False:\n        pass", "pipeline"),
]


def run(name, old, new, target, tmp):
    assert SRC.count(old) == 1, f"变异点不唯一或不存在：{name}"
    d = Path(tmp) / "src"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()
    (d / "video_review.py").write_text(SRC.replace(old, new), encoding="utf-8")
    shutil.copy(ROOT / "rubrics.json", d / "rubrics.json")
    env = {**os.environ, "VR_SRC": str(d), "PYTHONIOENCODING": "utf-8"}
    files = [str(p) for p in (ROOT / "tests").glob(f"test_{target}*.py")]
    p = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "-c", str(ROOT / "tests" / "pytest.ini"),
                        "-x", "-q", "--hypothesis-seed=0", *files], capture_output=True, text=True, env=env, cwd=ROOT)
    return p.returncode != 0, p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr[-200:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="")
    args = ap.parse_args()
    killed = survived = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, old, new, target in MUTANTS:
            if args.k not in name:
                continue
            t0 = time.time()
            dead, tail = run(name, old, new, target, tmp)
            killed += dead
            survived += not dead
            print(f"{'杀死' if dead else '存活'}  {name:<22} [{target}] {time.time() - t0:.0f}s  {tail}", flush=True)
    print(f"\n变异体 {killed + survived} 个：杀死 {killed}，存活 {survived}")
    sys.exit(1 if survived else 0)


if __name__ == "__main__":
    main()
