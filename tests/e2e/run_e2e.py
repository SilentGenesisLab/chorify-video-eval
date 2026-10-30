"""端到端评测：本地起评审网站，把 export_tvca.py 导出的用例经 HTTP 接口（multipart 上传）逐个提交，收回结果。

python tests/e2e/run_e2e.py [--cases %TEMP%/vr_e2e/cases.json] [--runs 3] [--workers 2] [--only id…]

走的是用户实际调用的路径：POST /api/v1/reviews/{stage} → 轮询 GET /api/v1/reviews/{id} → GET /report。
网站只监听 127.0.0.1，Token 每次随机生成；评审调用真实模型（会产生费用）。
结果写到 cases.json 同目录的 results/<case_id>.json，已有结果的用例跳过。
"""
import argparse
import json
import mimetypes
import os
import pathlib
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "review-site"
NEXT = SITE / "node_modules" / "next" / "dist" / "bin" / "next"
DEFAULT = pathlib.Path(tempfile.gettempdir()) / "vr_e2e" / "cases.json"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Site:
    def __init__(self, token, max_running):
        self.token, self.port = token, free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        env = {**os.environ, "NODE_ENV": "production", "NEXT_TELEMETRY_DISABLED": "1", "SITE_API_TOKEN": token,
               "PUBLIC_BASE_URL": self.base, "MAX_RUNNING": str(max_running), "PYTHON": sys.executable,
               "REVIEW_ROOT": str(ROOT), "PYTHONUTF8": "1", "RATE_LIMIT_BURST": "200"}
        env.pop("SITE_PASSWORD", None)
        self.log = open(pathlib.Path(tempfile.gettempdir()) / "vr_e2e_site.log", "ab")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.proc = subprocess.Popen(["node", str(NEXT), "start", "-p", str(self.port), "-H", "127.0.0.1"], cwd=SITE,
                                     env=env, stdout=self.log, stderr=self.log, creationflags=flags)
        for _ in range(300):
            try:
                if self.get("/api/v1/health")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.2)
        self.stop()
        raise RuntimeError("网站没有启动，见 %TEMP%/vr_e2e_site.log")

    def req(self, method, path, body=None, ctype=None, timeout=120):
        h = {"Authorization": f"Bearer {self.token}"}
        if ctype:
            h["Content-Type"] = ctype
        r = urllib.request.Request(self.base + path, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def get(self, path):
        return self.req("GET", path)

    def stop(self):
        if self.proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.kill()
        self.log.close()


def multipart(fields, files):
    """fields: [(name, str)]；files: [(field, path)]"""
    bd = uuid.uuid4().hex
    out = []
    for k, v in fields:
        out += [f"--{bd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode(), str(v).encode(), b"\r\n"]
    for k, p in files:
        p = pathlib.Path(p)
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        out += [f"--{bd}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{p.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode(),
                p.read_bytes(), b"\r\n"]
    out.append(f"--{bd}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={bd}"


def submit(site, case, runs):
    fields = [("title", case["case_id"][:80]), ("runs", runs), ("platform_hint", case["platform_hint"])]
    files = [("files", f) for f in case["files"]] + [("context", f) for f in case["context"]]
    tr = case.get("transcript")
    if tr and tr.endswith(".srt"):
        files.append(("files", tr))  # 接口文档：字幕 .srt 放 files 里会自动作为台词
    elif tr:
        fields.append(("transcript", pathlib.Path(tr).read_text(encoding="utf-8")))
    body, ctype = multipart(fields, files)
    st, raw = site.req("POST", f"/api/v1/reviews/{case['stage']}", body, ctype, timeout=600)
    if st not in (200, 202):
        raise RuntimeError(f"提交失败 {st}：{raw[:300]!r}")
    job = json.loads(raw)
    t0 = time.time()
    while job.get("status") in ("queued", "running"):
        if time.time() - t0 > 1800:
            raise RuntimeError("评审超过 30 分钟")
        time.sleep(5)
        st, raw = site.get(f"/api/v1/reviews/{job['id']}")
        job = json.loads(raw)
    if job.get("status") != "done":
        raise RuntimeError(f"评审失败：{job.get('error')}")
    st, rep = site.get(f"/api/v1/reviews/{job['id']}/report")
    return job, rep.decode("utf-8", "replace") if st == 200 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(DEFAULT))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    cases = json.loads(pathlib.Path(a.cases).read_text(encoding="utf-8"))
    if a.only:
        cases = [c for c in cases if c["case_id"] in a.only]
    out = pathlib.Path(a.cases).parent / "results"
    out.mkdir(exist_ok=True)
    todo = [c for c in cases if not (out / f"{c['case_id']}.json").exists()]
    print(f"{len(cases)} 例，待跑 {len(todo)} 例")
    if not todo:
        return
    site = Site(secrets.token_hex(16), a.workers)
    print(f"网站 {site.base} 已启动")

    def one(c):
        t0 = time.time()
        try:
            job, rep = submit(site, c, a.runs)
        except Exception as e:  # 一例失败不影响其他用例
            print(f"  {c['case_id']} 失败：{e}", flush=True)
            return
        (out / f"{c['case_id']}.json").write_text(json.dumps({"case": c, "job": job}, ensure_ascii=False, indent=1), encoding="utf-8")
        if rep:
            (out / f"{c['case_id']}.md").write_text(rep, encoding="utf-8")
        r = job.get("result") or {}
        print(f"  {c['case_id']}：{r.get('verdict')} {r.get('total')}（{time.time() - t0:.0f}s）", flush=True)

    try:
        with ThreadPoolExecutor(a.workers) as pool:
            list(pool.map(one, todo))
    finally:
        site.stop()


if __name__ == "__main__":
    main()
