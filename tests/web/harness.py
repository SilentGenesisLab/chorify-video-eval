"""C 层测试的网站驱动：构建一次网站、按不同环境变量启动隔离的 next start 实例、本地辅助服务。

- 构建：把 review-site 源码复制到临时目录构建，按源码 + next/react 版本哈希缓存；不碰工作区的 .next 与 data/
- 实例：每个实例一个目录（.next、node_modules 用目录联接共享），data/jobs 互不干扰
- 工作进程：PYTHON=当前解释器，PYTHONPATH=shim（sitecustomize 把模型地址指向本进程里的桩）
- 出网：HTTP(S)_PROXY 指向不可达端口、NO_PROXY 只放行回环，/health 查余额之类的外呼不会真的发出去
"""
import base64
import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE_SRC = Path(os.environ.get("C_SITE_SRC", ROOT / "review-site"))
NODE_MODULES = Path(os.environ.get("C_NODE_MODULES", SITE_SRC / "node_modules"))
TMP = Path(tempfile.gettempdir()) / "vr_site"
SHIM = Path(__file__).resolve().parent / "shim"
SOURCES = ["app", "lib", "worker", "docs", "middleware.js", "next.config.mjs", "jsconfig.json", "package.json"]
NEXT_BIN = Path("node_modules") / "next" / "dist" / "bin" / "next"


def link_dir(link, target):
    """Windows 用目录联接（不需要管理员权限），其他系统用符号链接。"""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _files(base):
    for name in SOURCES:
        p = base / name
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from sorted(x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts)


def versions():
    v = lambda p: json.loads((NODE_MODULES / p / "package.json").read_text(encoding="utf-8"))["version"]
    return {p: v(p) for p in ("next", "react", "react-dom")}


def build(src=SITE_SRC):
    """构建网站，返回构建目录。源码或依赖版本不变时直接复用。"""
    if not (NODE_MODULES / "next").exists():
        raise RuntimeError(f"{NODE_MODULES} 里没有 next，先在 {SITE_SRC} 执行 npm ci")
    h = hashlib.sha256(json.dumps(versions()).encode())
    for f in _files(src):
        h.update(str(f.relative_to(src)).encode())
        h.update(f.read_bytes())
    d = TMP / "build" / h.hexdigest()[:16]
    if (d / ".next" / "BUILD_ID").exists():
        return d
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for f in _files(src):
        (d / f.relative_to(src)).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, d / f.relative_to(src))
    link_dir(d / "node_modules", NODE_MODULES)
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
    for k in ("SITE_PASSWORD", "SITE_API_TOKEN", "PUBLIC_BASE_URL"):
        env.pop(k, None)
    p = subprocess.run(["node", str(NEXT_BIN), "build"], cwd=d, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode or not (d / ".next" / "BUILD_ID").exists():
        raise RuntimeError(f"next build 失败：\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    return d


def mini_root():
    """REVIEW_ROOT：评审器工程的只读副本（评分标准、框架文档、数据集、一轮结果），外加金丝雀：
    根目录 .env，以及和 dataset 同级、名字以 dataset 开头的 dataset-secret/（只按前缀比较根目录的实现会把它放出去）。"""
    d = TMP / "root"
    if (d / "ready-v3").exists():
        return d
    shutil.rmtree(d, ignore_errors=True)
    (d / "benchmark" / "results").mkdir(parents=True)
    for f in ("rubrics.json", "视频评审框架.md"):
        shutil.copy2(ROOT / f, d / f)
    shutil.copy2(ROOT / "benchmark" / "run_benchmark.py", d / "benchmark" / "run_benchmark.py")
    shutil.copytree(ROOT / "benchmark" / "dataset", d / "benchmark" / "dataset")
    shutil.copytree(ROOT / "benchmark" / "results" / "dev_v3", d / "benchmark" / "results" / "dev_v3")
    (d / ".env").write_text(f"DEEPSEEK_API_KEY={CANARY_KEY}\n", encoding="utf-8")
    (d / "benchmark" / "dataset-secret").mkdir()
    (d / "benchmark" / "dataset-secret" / "secret.json").write_text(CANARY_KEY, encoding="utf-8")
    # 用例详情页用 marked 渲染 .md（B68）：给一个副本里的材料追加原始 HTML 与 javascript: 链接
    md = d / "benchmark" / XSS_MD
    md.write_text(md.read_text(encoding="utf-8") + XSS_PAYLOAD, encoding="utf-8")
    (d / "ready-v3").touch()
    return d


CANARY_KEY = "sk-canary-must-never-leak"
XSS_CASE = "S08_creative_base"
XSS_MD = f"dataset/cases/{XSS_CASE}/creative.md"
XSS_PAYLOAD = '\n\n<img src=x onerror="window.__mdxss=1">\n\n[点我](javascript:window.__mdxss=2)\n'


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def kill_tree(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        import signal
        os.killpg(pid, signal.SIGKILL)


class Response:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.body)

    def __repr__(self):
        return f"<{self.status} {self.body[:200]!r}>"


class Site:
    """一个 next start 实例。env 覆盖默认环境；同一 home 目录重启即可测『服务重启』。"""

    def __init__(self, build_dir, env, stub_url, home=None, name="site"):
        self.build_dir, self.extra_env, self.stub_url = build_dir, env, stub_url
        self.home = home or TMP / "inst" / f"{name}-{uuid.uuid4().hex[:8]}"
        self.proc = None
        if not self.home.exists():
            self.home.mkdir(parents=True)
            for n in (".next", "node_modules", "docs"):
                link_dir(self.home / n, (build_dir / n).resolve())
            shutil.copytree(build_dir / "worker", self.home / "worker")
            for n in ("package.json", "next.config.mjs"):
                shutil.copy2(build_dir / n, self.home / n)
            # 和 data/jobs 同级、名字以 jobs 开头的金丝雀目录
            (self.home / "data" / "jobs-secret").mkdir(parents=True)
            (self.home / "data" / "jobs-secret" / "secret.json").write_text(CANARY_KEY, encoding="utf-8")
        self.jobs = self.home / "data" / "jobs"
        self.root = mini_root()

    def env(self):
        e = {k: v for k, v in os.environ.items()
             if k.upper() not in ("SITE_PASSWORD", "SITE_API_TOKEN", "PUBLIC_BASE_URL", "PYTHON", "REVIEW_ROOT",
                                  "MAX_RUNNING", "DEEPSEEK_API_KEY", "PYTHONPATH", "NODE_OPTIONS", "SSRF_ALLOW_HOSTS")}
        e.update({
            "NODE_ENV": "production", "NEXT_TELEMETRY_DISABLED": "1",
            "REVIEW_ROOT": str(self.root), "PYTHON": sys.executable, "PYTHONPATH": str(SHIM), "PYTHONUTF8": "1",
            "C_STUB_URL": self.stub_url, "C_REAL_ROOT": str(ROOT), "DEEPSEEK_API_KEY": "sk-test",
            # 任何非回环外呼都打到不可达代理上，测试不会访问公网
            "NODE_USE_ENV_PROXY": "1", "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        e.update({k: v for k, v in self.extra_env.items() if v is not None})
        for k in [k for k, v in self.extra_env.items() if v is None]:
            e.pop(k, None)
        return e

    def start(self, timeout=60):
        self.port = free_port()
        self.log = open(self.home / "server.log", "ab")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.proc = subprocess.Popen(["node", str(NEXT_BIN), "start", "-p", str(self.port), "-H", "127.0.0.1"],
                                     cwd=self.home, env=self.env(), stdout=self.log, stderr=self.log,
                                     creationflags=flags, start_new_session=os.name != "nt")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"next start 退出：{self.server_log()[-2000:]}")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("next start 启动超时")
        self.request("GET", "/favicon.ico")  # 预热
        return self

    def stop(self):
        if self.proc and self.proc.poll() is None:
            kill_tree(self.proc.pid)
            self.proc.wait(10)
        if self.proc:
            self.log.close()
        self.proc = None

    def server_log(self):
        return (self.home / "server.log").read_text(encoding="utf-8", errors="replace")

    def request(self, method, path, headers=None, body=None, timeout=60):
        """原样发送 path（不做规范化），便于测路径穿越。body 为 dict/list 时按 JSON 发送。"""
        headers = dict(headers or {})
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            body = body.encode()
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            c.request(method, path, body=body, headers=headers)
            r = c.getresponse()
            return Response(r.status, {k.lower(): v for k, v in r.getheaders()}, r.read())
        finally:
            c.close()


class _Server:
    def __init__(self, handler_cls):
        import http.server
        import threading
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.srv.daemon_threads = True
        self.srv.owner = self
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def url(self, path=""):
        return f"http://127.0.0.1:{self.port}{path}"

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def _handler(fn_get=None, fn_post=None):
    import http.server

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            fn_get(self, self.server.owner)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            fn_post(self, self.server.owner, self.rfile.read(n))

        def log_message(self, *a):
            pass

        def send(self, status, data, ctype="application/json", extra=None):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

    return H


def _all_dims():
    r = json.loads((ROOT / "rubrics.json").read_text(encoding="utf-8"))
    return [d["id"] for s in r["stages"].values() for d in s["dimensions"]]


class StubModel(_Server):
    """工作进程用的模型桩。按材料里的标记决定行为，任务之间互不影响：

    __402__ 余额不足；__slow__ 每次采样等 C_SLOW 秒；__hit__ 所有采样命中 R1；
    __xss__ 总评里带 HTML。其余情况每个维度 4 分、无红线。
    """
    SLOW = 4.0

    def __init__(self):
        self.calls = []
        self.dims = _all_dims()

        def post(h, me, raw):
            text = json.dumps(json.loads(raw), ensure_ascii=False)  # 请求体里中文是 \uXXXX 转义的
            me.calls.append(text)
            if "__402__" in text:
                return h.send(402, {"error": {"message": "Insufficient Balance"}})
            if "__slow__" in text:
                time.sleep(me.SLOW)
            hit = "__hit__" in text
            summary = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>' if "__xss__" in text else "总评"
            run = {"dimensions": [{"id": d, "score": 4, "evidence": "证据", "issues": ["问题"], "suggestions": ["建议"]}
                                  for d in me.dims],
                   "redlines": [{"id": f"R{i}", "hit": hit and i == 1, "evidence": "红线证据"} for i in range(1, 6)],
                   "highlights": ["亮点"], "top_fixes": ["改法"], "summary": summary}
            h.send(200, {"choices": [{"message": {"content": json.dumps(run, ensure_ascii=False)}}],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

        super().__init__(_handler(fn_post=post))


class Helper(_Server):
    """回调接收、SSRF 金丝雀、下载源。

    GET  /file/<name>        小文件（PNG 头）
    GET  /canary/<name>      金丝雀：被访问即说明服务端请求了内网地址
    GET  /redirect?to=<url>  302 跳转
    GET  /chunked/<mb>/<name> 分块传输、不带 Content-Length 的大文件
    GET  /sized/<mb>/<name>  带 Content-Length 的大文件，边发边计数（客户端提前断开就停）
    POST /cb                 记录回调
    """

    def __init__(self):
        self.callbacks, self.canary, self.chunked_sent, self.sized_sent = [], [], 0, 0

        def get(h, me, *_):
            from urllib.parse import parse_qs, urlparse
            u = urlparse(h.path)
            if u.path.startswith("/canary/"):
                me.canary.append(h.path)
                return h.send(200, b"\x89PNG\r\n\x1a\ncanary", "image/png")
            if u.path.startswith("/file/"):
                return h.send(200, b"\x89PNG\r\n\x1a\nfile", "image/png")
            if u.path == "/redirect":
                return h.send(302, b"", extra={"Location": parse_qs(u.query)["to"][0]})
            if u.path.startswith("/chunked/"):
                mb = int(u.path.split("/")[2])
                h.send_response(200)
                h.send_header("Content-Type", "video/mp4")
                h.send_header("Transfer-Encoding", "chunked")
                h.end_headers()
                block = b"\0" * (1 << 20)
                try:
                    for _ in range(mb):
                        h.wfile.write(b"%x\r\n%s\r\n" % (len(block), block))
                        me.chunked_sent += len(block)
                    h.wfile.write(b"0\r\n\r\n")
                except OSError:
                    pass
                return
            if u.path.startswith("/sized/"):
                mb = int(u.path.split("/")[2])
                h.send_response(200)
                h.send_header("Content-Type", "video/mp4")
                h.send_header("Content-Length", str(mb << 20))
                h.end_headers()
                block = b"\0" * (1 << 20)
                try:
                    for _ in range(mb):
                        h.wfile.write(block)
                        me.sized_sent += len(block)
                except OSError:
                    pass
                return
            h.send(404, b"no")

        def post(h, me, raw):
            me.callbacks.append({"path": h.path, "body": json.loads(raw or b"null")})
            h.send(200, {"ok": True})

        super().__init__(_handler(fn_get=get, fn_post=post))


def wait_for(fn, timeout=30, interval=0.3):
    deadline = time.time() + timeout
    while True:
        v = fn()
        if v or time.time() > deadline:
            return v
        time.sleep(interval)


def basic(pw, user="u"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def multipart(parts):
    """parts：[(字段名, 文件名或 None, bytes)]。返回 (body, Content-Type)。"""
    bnd = uuid.uuid4().hex
    body = b"".join(
        f'--{bnd}\r\nContent-Disposition: form-data; name="{n}"{f"; filename=\"{fn}\"" if fn else ""}\r\n\r\n'.encode() + v + b"\r\n"
        for n, fn, v in parts) + f"--{bnd}--\r\n".encode()
    return body, f"multipart/form-data; boundary={bnd}"
