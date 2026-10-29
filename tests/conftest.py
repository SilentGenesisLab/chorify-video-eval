"""A 层（确定性层）测试的公共夹具：被测代码路径、评分标准、模型桩服务器、断网保护。

运行：.venv/Scripts/python -X utf8 -m pytest tests
"""
import http.server
import json
import os
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# 变异测试时用 VR_SRC 指向被改过的源码副本
SRC = Path(os.environ.get("VR_SRC", ROOT))
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import video_review  # noqa: E402


def pytest_configure(config):
    # 产品代码多处读写文件不指定编码（B01），非 UTF-8 模式下大量用例会因环境而非逻辑失败。
    # B01 本身由 test_encoding.py 用子进程单独验证。
    if not sys.flags.utf8_mode:
        pytest.exit("请用 UTF-8 模式运行：python -X utf8 -m pytest tests", returncode=4)


@pytest.fixture(scope="session")
def rubric():
    return json.loads((SRC / "rubrics.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """默认把模型地址指向不可达端口，任何用例都不可能真实调用付费接口。"""
    monkeypatch.setattr(video_review, "api_url", lambda: "http://127.0.0.1:9/never")
    for k in ("REVIEW_API_URL", "REVIEW_API_KEY", "REVIEW_MODEL", "REVIEW_MAX_CALLS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)


def completion(content, usage=None):
    """OpenAI 兼容格式的模型响应。content 为 dict 时序列化成 JSON 字符串。"""
    if isinstance(content, (dict, list)):
        content = json.dumps(content, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20}}


class StubLLM:
    """本地 HTTP 桩：按顺序返回预设响应，记录每个请求体。"""

    def __init__(self):
        self.queue = []
        self.default = None
        self.requests = []
        self.sleeps = []
        self.lock = threading.Lock()

    def push(self, body, status=200):
        """body：dict 按 JSON 返回；str/bytes 原样返回。"""
        self.queue.append((body, status))

    def next(self):
        with self.lock:
            if self.queue:
                return self.queue.pop(0)
            if self.default is not None:
                return self.default, 200
            return {"error": "stub queue empty"}, 500


@pytest.fixture
def stub_llm(monkeypatch):
    stub = StubLLM()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n)
            with stub.lock:
                stub.requests.append({"headers": dict(self.headers), "body": json.loads(raw)})
            body, status = stub.next()
            data = body if isinstance(body, bytes) else (body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode())
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/chat/completions"
    monkeypatch.setattr(video_review, "api_url", lambda: url)
    monkeypatch.setattr(video_review.time, "sleep", stub.sleeps.append)
    yield stub
    srv.shutdown()
    srv.server_close()


def make_run(rubric, stage, scores, hits=(), *, evidence=None, summary="总评", top_fixes=None, extra_redlines=None):
    """构造一次模型采样。scores 为 list（按维度顺序）或 dict（id→分）；hits 为命中的红线 id。"""
    dims = rubric["stages"][stage]["dimensions"]
    if isinstance(scores, dict):
        pairs = [(d["id"], scores[d["id"]]) for d in dims if d["id"] in scores]
    else:
        pairs = [(d["id"], s) for d, s in zip(dims, scores)]
    n_red = len(rubric["stages"][stage]["redlines"])
    reds = [{"id": f"R{i + 1}", "hit": f"R{i + 1}" in hits, "evidence": f"R{i + 1} 证据"} for i in range(n_red)]
    return {"dimensions": [{"id": i, "score": s, "evidence": (evidence or {}).get(i, f"{i} 证据"),
                            "issues": [f"{i} 问题"], "suggestions": [f"{i} 建议"]} for i, s in pairs],
            "redlines": reds + list(extra_redlines or []),
            "highlights": ["亮点"], "top_fixes": top_fixes or ["改法 1"], "summary": summary}
