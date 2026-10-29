"""B 层（模型判断评测）公共部分：路径、标签加载、统计工具、费用估算。

数据根目录 DATA：标签里的 dataset/... 相对它解析。png/mp4 不进 git，需用 build_dataset.py 在副本里重新生成，
用 VR_BENCH_DATA 指向副本的 benchmark/ 目录；未设置时依次尝试 %TEMP%/vr_bench/src/benchmark、仓库 benchmark/。
探针用例（probes/...）相对 tests/bench 解析，材料是纯文本、随仓库提交。
"""
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark"))

STAGES = ["creative", "storyboard", "asset", "video"]
RUBRIC = json.loads((ROOT / "rubrics.json").read_text(encoding="utf-8"))
PROBES = BENCH / "probes"
RESULTS = BENCH / "results"
# 第二轮用例（cases_v2.py 生成）：v2/labels.jsonl、v2/meta.json 与 v2/cases/ 下的文本随仓库提交；
# 同目录的图片 / 视频不进 git（约 3GB），cases_v2.py 重新生成，已存在的跳过
V2 = BENCH / "v2"
# 公开数据集（KonIQ-10k、ImageRewardDB、VideoFeedback）下载到仓库外，标签里用 ext/... 引用
EXT = Path(os.environ.get("VR_BENCH_EXT") or Path(tempfile.gettempdir()) / "vr_bench" / "ext")
# Z:\ 的真实项目素材（客户材料）：复制和生成的用例、标签都放仓库外，标签里用 real/... 引用，不进 git / zip
REAL = Path(os.environ.get("VR_BENCH_REAL") or Path(tempfile.gettempdir()) / "vr_bench" / "real")

# 费用：DeepSeek 按 token 计费。test_v1 共 1,677,002 输入 + 1,972,176 输出 token，实付约 ¥10.8，
# 折合约 ¥2.96 / 百万 token（输入输出混合）。只用于预估和预算闸门；实际花费以运行前后的账户余额差为准。
CNY_PER_MTOKEN = float(os.environ.get("VR_BENCH_CNY_PER_MTOKEN", "2.96"))
# 每次采样的预估 token（按 test_v1 各关卡实测均值取整）
EST_TOKENS = {"creative": 7000, "storyboard": 9500, "asset": 12500, "video": 22000}


def data_root():
    cands = [os.environ.get("VR_BENCH_DATA"), Path(tempfile.gettempdir()) / "vr_bench" / "src" / "benchmark",
             ROOT / "benchmark"]
    for c in cands:
        if c and (Path(c) / "dataset" / "labels.jsonl").exists():
            return Path(c)
    raise SystemExit("找不到数据集")


def resolve(rel, data=None):
    """标签里的相对路径 → 绝对路径。"""
    rel = rel.replace("\\", "/")
    if rel.startswith(("probes/", "v2/")):
        return BENCH / rel
    if rel.startswith("ext/"):
        return EXT / rel[4:]
    if rel.startswith("real/"):
        return REAL / rel[5:]
    return (data or data_root()) / rel


def load_main(data=None):
    p = (data or data_root()) / "dataset" / "labels.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_probes():
    p = PROBES / "labels.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_v2():
    """第二轮标签：合成用例（v2/labels.jsonl）+ 真实素材用例（REAL/labels.jsonl，仓库外）。"""
    out = []
    for p in (V2 / "labels.jsonl", REAL / "labels.jsonl"):
        if p.exists():
            out += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return out


def load_all(data=None):
    return load_main(data) + load_probes() + load_v2()


def load_round1(data=None):
    """第一轮的标签（主集 + 探针）；score.py 的覆盖率按它算，否则第二轮用例全算成"缺结果"。"""
    return load_main(data) + load_probes()


def stage_rubric(stage):
    return RUBRIC["stages"][stage]


def dim_ids(stage):
    return [d["id"] for d in stage_rubric(stage)["dimensions"]]


def redline_ids(stage):
    return [f"R{i + 1}" for i in range(len(stage_rubric(stage)["redlines"]))]


# ---------------- 统计 ----------------

def wilson(k, n, z=1.96):
    """二项比例的 Wilson 95% 置信区间 (lo, hi)；n=0 返回 (None, None)。"""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def rate(flags):
    """[bool] → {"k","n","rate","lo","hi"}，None 视为缺失、不计入 n。"""
    v = [bool(x) for x in flags if x is not None]
    k, n = sum(v), len(v)
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n if n else None, "lo": lo, "hi": hi}


# 同一批用例原样重跑一次的波动（第一轮 results/b1/r1 vs r2，72 例）：判定变了 4 例，总分差 p95 0.36。
# 有 --compare 时 score.py 用实测值，没有时用这组。"内容没变 / 注入不该起作用"的比较都要先扣掉这部分。
NOISE = {"verdict_flip": 0.056, "total_p95": 0.36}
MIN_N = 10  # 样本少于这个数的比率只报告，不判通过 / 未通过（n=6 时 ≥0.85 等于不许错一个）


def gate_state(m, t):
    """按一条门槛判一个指标：返回 (状态, 取值)。状态：
    pass / fail；unsure = 点估计没达标但 95% 区间跨过门槛（样本不足以下结论）；small = n < MIN_N；None = 无值。
    只有比率（带 lo / hi）做区间判定，其余按点估计。"""
    field = t["field"]
    x = m.get(field) if isinstance(m, dict) else m
    if x is None:
        return None, None
    ok = ("min" not in t or x >= t["min"]) and ("max" not in t or x <= t["max"])
    if field != "rate" or not isinstance(m, dict) or "lo" not in m:
        return ("pass" if ok else "fail"), x
    if m["n"] < MIN_N:
        return "small", x
    if ok:
        return "pass", x
    clearly = ("min" in t and m["hi"] < t["min"]) or ("max" in t and m["lo"] > t["max"])
    return ("fail" if clearly else "unsure"), x


def bootstrap_mean_ci(xs, iters=4000, seed=0):
    if not xs:
        return None, None
    rnd = random.Random(seed)
    n = len(xs)
    ms = sorted(sum(rnd.choice(xs) for _ in range(n)) / n for _ in range(iters))
    return ms[int(iters * 0.025)], ms[int(iters * 0.975) - 1]


def mcnemar_exact(b, c):
    """配对二分类结果的精确 McNemar 检验（双侧）：b = 只在 A 成立，c = 只在 B 成立。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def half_up(x):
    """四舍五入到整数（不用 round 的银行家舍入，见 B29）。"""
    return int(math.floor(x + 0.5))


def qwk(a, b, k=5):
    """二次加权 kappa，分数取 1..k 的整数；范围外直接报错（不静默错位，见 B21）。"""
    if len(a) != len(b) or not a:
        raise ValueError("长度不一致或为空")
    for x in list(a) + list(b):
        if not (isinstance(x, int) and 1 <= x <= k):
            raise ValueError(f"分数越界：{x!r}")
    n = len(a)
    O = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        O[x - 1][y - 1] += 1
    ha = [sum(1 for x in a if x == i + 1) for i in range(k)]
    hb = [sum(1 for y in b if y == i + 1) for i in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * O[i][j]
            den += w * ha[i] * hb[j] / n
    return 1.0 if den == 0 else 1 - num / den


def cost_cny(usage):
    return (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)) / 1e6 * CNY_PER_MTOKEN
