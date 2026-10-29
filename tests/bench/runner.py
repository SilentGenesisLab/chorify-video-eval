"""B 层运行器：把产品的 video_review.evaluate 当库调用，结果写到 tests/bench/results/<name>/<round>/<case_id>.json。

python tests/bench/runner.py --name b1 --sets main probes --runs 3 --max-cost 40 --dry-run   # 只估算
python tests/bench/runner.py --name b1 --sets main probes --runs 3 --max-cost 40
python tests/bench/runner.py --name b1 --preset stability --round r2                          # 复测子集，第二轮

- 已有结果的用例跳过（中断后重跑即续跑）；失败的用例不写文件，下次重跑会重试。
- --max-cost 是预算闸门：按已花 token 折算的费用加上剩余用例的预估费用超过上限时，不再提交新用例。
- 运行前后各查一次 DeepSeek 账户余额，差值写进 spend.json，作为实际花费。
"""
import argparse
import json
import sys
import threading
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import (EST_TOKENS, CNY_PER_MTOKEN, RESULTS, STAGES, cost_cny, data_root, load_main, load_probes, load_v2,
                    resolve)

import video_review  # noqa: E402

# 稳定性子集：每个测试场景每关取基准 + 一个红线用例 + 一个质量用例
STABILITY_VARIANTS = {"creative": ["base", "cr_extreme", "cr_no_cta"], "storyboard": ["base", "sb_danger", "sb_no_sound"],
                      "asset": ["base", "as_font", "as_blur"], "video": ["base", "v_black", "v_quiet"]}


def select(args):
    rows = []
    if "main" in args.sets:
        rows += [l for l in load_main() if l["split"] == "test"]
    if "probes" in args.sets:
        rows += load_probes()
    if "v2" in args.sets:
        rows += load_v2()
    if args.families:
        rows = [l for l in rows if l.get("family") in args.families]
    if args.preset == "stability":
        rows = [l for l in load_main() if l["split"] == "test" and l["variant"] in STABILITY_VARIANTS[l["stage"]]]
    if args.stages:
        rows = [l for l in rows if l["stage"] in args.stages]
    if args.kinds:
        rows = [l for l in rows if l["kind"] in args.kinds]
    if args.probe:
        rows = [l for l in rows if l.get("probe") in args.probe]
    if args.cases:
        rows = [l for l in rows if l["case_id"] in args.cases]
    return rows[:args.limit] if args.limit else rows


IMG_TOKENS = 2400  # 资产关每多一张图的 token（按第一轮 4 张图 12.5k 粗估，未单独测过）


def est(label, runs, data=None):
    """每例预估：关卡均值 + 超出第一轮规模的部分（多出的图、长文本按 UTF-8 字节 / 1.5）。"""
    inp = label["inputs"]
    imgs = [f for f in inp["files"] if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    text = sum(resolve(f, data).stat().st_size for f in inp["files"] + inp.get("context", [])
               if f.lower().endswith((".md", ".txt", ".srt")) and resolve(f, data).exists())
    tokens = EST_TOKENS[label["stage"]] + max(0, len(imgs) - 4) * IMG_TOKENS + max(0, text - 6000) / 1.5
    return tokens * runs / 1e6 * CNY_PER_MTOKEN


def balance(key):
    try:
        req = urllib.request.Request("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"})
        info = json.loads(urllib.request.urlopen(req, timeout=20).read())
        return sum(float(b["total_balance"]) for b in info.get("balance_infos", []) if b.get("currency") == "CNY")
    except Exception as e:  # 余额查询失败不影响评测，只是拿不到实际花费
        print(f"余额查询失败：{e}", file=sys.stderr)
        return None


def run_case(lab, args, key, data):
    inp = lab["inputs"]
    t0 = time.time()
    ev = video_review.evaluate(
        lab["stage"], [str(resolve(f, data)) for f in inp["files"]], [str(resolve(c, data)) for c in inp.get("context", [])],
        str(resolve(inp["transcript"], data)) if inp.get("transcript") else None, args.runs, args.model, args.effort,
        platform_hint=inp.get("platform_hint", video_review.DEFAULT_PLATFORM_HINT), key=key)
    ev.update(seconds=round(time.time() - t0, 1), case_id=lab["case_id"], runs=args.runs, model=args.model,
              effort=args.effort, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--round", default="r1")
    ap.add_argument("--sets", nargs="*", default=["main", "probes"], choices=["main", "probes", "v2"])
    ap.add_argument("--families", nargs="*", help="只跑第二轮的部分子集（如 b9 e3）")
    ap.add_argument("--preset", choices=["stability"])
    ap.add_argument("--stages", nargs="*", choices=STAGES)
    ap.add_argument("--kinds", nargs="*")
    ap.add_argument("--probe", nargs="*")
    ap.add_argument("--cases", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-cost", type=float, default=40.0, help="预算上限（元）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = data_root()
    out = RESULTS / args.name / args.round
    labels = select(args)
    todo = [l for l in labels if not (out / f"{l['case_id']}.json").exists()]
    missing = [f for l in todo
               for f in l["inputs"]["files"] + l["inputs"].get("context", []) +
               ([l["inputs"]["transcript"]] if l["inputs"].get("transcript") else [])
               if not resolve(f, data).exists()]
    if missing:
        sys.exit(f"缺少材料 {len(missing)} 个（如 {missing[0]}）：先用 build_dataset.py 生成媒体，或设置 VR_BENCH_DATA")
    estimate = sum(est(l, args.runs, data) for l in todo)
    by_stage = {s: sum(1 for l in todo if l["stage"] == s) for s in STAGES}
    print(f"数据：{data}\n选中 {len(labels)} 例，待运行 {len(todo)} 例 {by_stage}，每例 {args.runs} 次采样，"
          f"预估 ¥{estimate:.1f}（预算 ¥{args.max_cost}）", file=sys.stderr)
    if args.dry_run or not todo:
        return

    key = video_review.load_api_key()
    out.mkdir(parents=True, exist_ok=True)
    (out.parent / "run_spec.json").write_text(json.dumps({**vars(args), "data": str(data)}, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    bal0, t0 = balance(key), time.time()
    spent, inflight, lock, stop = 0.0, 0.0, threading.Lock(), threading.Event()
    ok = failed = skipped = 0

    def guarded(lab):
        # 已花费 + 正在跑的用例预估 + 本例预估 超过预算就不再提交
        nonlocal inflight
        e = est(lab, args.runs, data)
        with lock:
            if stop.is_set() or spent + inflight + e > args.max_cost:
                stop.set()
                return None
            inflight += e
        try:
            return run_case(lab, args, key, data)
        finally:
            with lock:
                inflight -= e

    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(guarded, l): l for l in todo}
        for i, f in enumerate(as_completed(futs), 1):
            lab = futs[f]
            try:
                ev = f.result()
                if ev is None:
                    skipped += 1
                    continue
                (out / f"{lab['case_id']}.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
                with lock:
                    spent += cost_cny(ev["usage"])
                ok += 1
                r = ev["result"]
                print(f"[{i}/{len(todo)}] {lab['case_id']}: {r['verdict']} {r['total']} ¥{spent:.2f}", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"[{i}/{len(todo)}] {lab['case_id']} 失败：{e}", file=sys.stderr)
                traceback.print_exc()
                if "鉴权或余额" in str(e):
                    stop.set()
    bal1 = balance(key)
    spend = {"round": args.round, "ok": ok, "failed": failed, "skipped_by_budget": skipped,
             "estimated_cny": round(spent, 2), "balance_before": bal0, "balance_after": bal1,
             "actual_cny": round(bal0 - bal1, 2) if bal0 is not None and bal1 is not None else None,
             "minutes": round((time.time() - t0) / 60, 1)}
    log = out.parent / "spend.json"
    hist = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    log.write_text(json.dumps(hist + [spend], ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(spend, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
