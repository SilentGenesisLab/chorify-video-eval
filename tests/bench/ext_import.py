"""e1 效果评测的公开数据集：从 ModelScope 镜像下载，按人工评分分层抽样，放到仓库外的 VR_BENCH_EXT（默认 %TEMP%/vr_bench/ext）。

  KonIQ-10k       真实照片，众包画质 MOS（1–5）                      → 资产关 A2
  ImageRewardDB   AI 生成图片，人工 fidelity / 图文一致 / 总体评分（1–7） → 资产关 A2、A5
  VideoFeedback   AI 生成视频，人工 visual quality / 时序一致 / 文本对齐（1–4） → 成片关 V3、V2、V6

python tests/bench/ext_import.py            # 下载 + 抽样，写 ext/manifest.json；已下载的文件跳过
Hugging Face 在本机网络不可达，用 ModelScope 镜像；镜像的许可字段与原始许可可能不同，manifest 里两者都记。
"""
import csv
import hashlib
import io
import json
import random
import sys
import time
import urllib.parse
import urllib.request
import zipfile

from PIL import Image

from common import EXT

API = "https://www.modelscope.cn/api/v1/datasets/{ns}/{name}/repo?Revision=master&FilePath={path}"
SEED = 20261028
SOURCES = {
    "koniq": {"repo": "Xinary/KONIQ", "license": "原始 CC BY-NC-ND 4.0（镜像标 Apache-2.0）", "paper": "Hosu et al., TIP 2020"},
    "irdb": {"repo": "ZhipuAI/ImageRewardDB", "license": "Apache-2.0", "paper": "Xu et al., NeurIPS 2023"},
    "vf": {"repo": "TIGER-Lab/VideoFeedback", "license": "Apache-2.0", "paper": "He et al., EMNLP 2024 (VideoScore)"},
}
N_KONIQ, N_IRDB, N_VF, N_PAIRS = 60, 60, 40, 10


def fetch(repo, path, dst, retries=4):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    ns, name = repo.split("/")
    url = API.format(ns=ns, name=name, path=urllib.parse.quote(path))
    for i in range(retries):
        try:
            tmp = dst.with_suffix(dst.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            tmp.replace(dst)
            return dst
        except Exception as e:  # 网络抖动重试
            print(f"  下载失败（{i + 1}/{retries}）{path}：{e}", file=sys.stderr)
            time.sleep(2 ** i)
    raise RuntimeError(f"下载失败：{repo}/{path}")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def spread(rows, key, n):
    """按评分排序后等间距取 n 个：覆盖整个分数范围，而不是集中在均值附近。"""
    rows = sorted(rows, key=key)
    step = (len(rows) - 1) / (n - 1)
    return [rows[round(i * step)] for i in range(n)]


def balanced(rows, key, n, rnd):
    """离散评分：每个分数档取差不多的数量。"""
    by = {}
    for r in rows:
        by.setdefault(key(r), []).append(r)
    levels = sorted(by)
    out, i = [], 0
    while len(out) < n and any(by.values()):
        lv = levels[i % len(levels)]
        if by[lv]:
            out.append(by[lv].pop(rnd.randrange(len(by[lv]))))
        i += 1
    return out


def koniq():
    d = EXT / "koniq"
    rows = list(csv.DictReader(io.StringIO(fetch(SOURCES["koniq"]["repo"], "koniq10k_scores_and_distributions.csv",
                                                 d / "scores.csv").read_text(encoding="utf-8"))))
    pick = spread(rows, lambda r: float(r["MOS"]), N_KONIQ)
    out = []
    for r in pick:
        p = fetch(SOURCES["koniq"]["repo"], f"1024x768/{r['image_name']}", d / r["image_name"])
        out.append({"id": f"koniq_{p.stem}", "source": "koniq", "file": f"ext/koniq/{p.name}", "sha256": sha(p),
                    "scores": {"MOS": round(float(r["MOS"]), 3), "SD": round(float(r["SD"]), 3), "n_raters": int(r["c_total"])}})
    return out


def irdb():
    d = EXT / "irdb"
    z = fetch(SOURCES["irdb"]["repo"], "images/test/test_1.zip", d / "test_1.zip")
    with zipfile.ZipFile(z) as zf:
        meta_name = next(n for n in zf.namelist() if n.endswith(".json"))
        meta = json.loads(zf.read(meta_name))
        rnd = random.Random(SEED)
        # 每个提示词只取一张，避免同一提示词的图互相牵连
        by_prompt = {}
        for m in meta:
            by_prompt.setdefault(m["prompt_id"], []).append(m)
        one = [rnd.choice(v) for _, v in sorted(by_prompt.items())]
        pick = balanced(one, lambda m: m["fidelity_rating"], N_IRDB, rnd)
        names = {n.rsplit("/", 1)[-1]: n for n in zf.namelist()}
        # e2 偏序对：同一提示词下 fidelity 差 ≥ 3 的最好 / 最差两张（人工评分给出的天然好坏对）
        pairs = []
        for pid, v in sorted(by_prompt.items()):
            hi, lo = max(v, key=lambda m: m["fidelity_rating"]), min(v, key=lambda m: m["fidelity_rating"])
            if hi["fidelity_rating"] - lo["fidelity_rating"] >= 3 and len(pairs) < N_PAIRS:
                pairs.append((pid, hi, lo))
        pick = pick + [m for _, hi, lo in pairs for m in (hi, lo) if m not in pick]
        out = []
        for m in pick:
            stem = m["image_path"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
            dst = d / f"{stem}.png"
            if not dst.exists():
                # 产品按扩展名猜 MIME，webp 能否被模型接口接受没验证过，统一转成无损 PNG
                Image.open(io.BytesIO(zf.read(names[m["image_path"].rsplit("/", 1)[-1]]))).convert("RGB").save(dst)
            out.append({"id": f"irdb_{stem[:8]}", "source": "irdb", "file": f"ext/irdb/{dst.name}", "sha256": sha(dst),
                        "prompt": m["prompt"].strip(), "category": m.get("classification"),
                        "scores": {"overall": m["overall_rating"], "fidelity": m["fidelity_rating"],
                                   "alignment": m["image_text_alignment_rating"]},
                        "pair": next((f"irdbpair_{pid}" for pid, hi, lo in pairs if m in (hi, lo)), None),
                        "pair_role": next(("hi" if m is hi else "lo" for pid, hi, lo in pairs if m in (hi, lo)), None),
                        "in_e1": m in pick[:N_IRDB]})
    return out


def vf():
    d = EXT / "vf"
    meta = json.loads(fetch(SOURCES["vf"]["repo"], "test/data_annotated.json", d / "data_annotated.json").read_text(encoding="utf-8"))
    z = fetch(SOURCES["vf"]["repo"], "test/videos_annotated.zip", d / "videos_annotated.zip")
    with zipfile.ZipFile(z) as zf:
        vids = {n.rsplit("/", 1)[-1].rsplit(".", 1)[0]: n for n in zf.namelist() if n.lower().endswith(".mp4")}
        rows = [m for m in meta if m["id"] in vids]
        pick = balanced(rows, lambda m: m["visual quality"], N_VF, random.Random(SEED))
        out = []
        for m in pick:
            dst = d / f"{m['id']}.mp4"
            if not dst.exists():
                dst.write_bytes(zf.read(vids[m["id"]]))
            out.append({"id": f"vf_{m['id']}", "source": "vf", "file": f"ext/vf/{dst.name}", "sha256": sha(dst),
                        "prompt": m["text prompt"].strip(),
                        "scores": {"visual": m["visual quality"], "temporal": m["temporal consistency"],
                                   "dynamic": m["dynamic degree"], "alignment": m["text-to-video alignment"],
                                   "factual": m["factual consistency"]}})
    return out


def main():
    EXT.mkdir(parents=True, exist_ok=True)
    items = []
    for name, fn in (("koniq", koniq), ("irdb", irdb), ("vf", vf)):
        print(f"[{name}] …", file=sys.stderr)
        got = fn()
        print(f"[{name}] {len(got)} 个", file=sys.stderr)
        items += got
    man = {"sources": SOURCES, "seed": SEED, "items": items}
    (EXT / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {EXT / 'manifest.json'}：{len(items)} 个", file=sys.stderr)


if __name__ == "__main__":
    main()
