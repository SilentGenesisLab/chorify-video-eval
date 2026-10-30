"""call_model：请求体、响应解析、重试与停止条件。用本地桩服务器代替模型接口。"""
import json
import urllib.request

import pytest

import video_review as vr
from bugs import bug
from conftest import completion

OK = {"dimensions": [], "redlines": []}


def call(effort="high", retries=3):
    return vr.call_model("sk-test", "deepseek-flash", "系统提示", [{"type": "text", "text": "材料"}], effort, retries)


def test_request_body_and_headers(stub_llm):
    stub_llm.push(completion(OK))
    call()
    req = stub_llm.requests[0]
    body = req["body"]
    assert req["headers"]["Authorization"] == "Bearer sk-test"
    assert body["model"] == "deepseek-flash" and body["temperature"] == 0.2
    assert body["response_format"] == {"type": "json_object"} and body["reasoning_effort"] == "high"
    assert body["messages"] == [{"role": "system", "content": "系统提示"},
                                {"role": "user", "content": [{"type": "text", "text": "材料"}]}]


def test_no_effort_field_when_effort_empty(stub_llm):
    stub_llm.push(completion(OK))
    call(effort=None)
    assert "reasoning_effort" not in stub_llm.requests[0]["body"]


def test_returns_parsed_json_and_usage(stub_llm):
    stub_llm.push(completion(OK, {"prompt_tokens": 7, "completion_tokens": 3}))
    assert call() == (OK, {"prompt_tokens": 7, "completion_tokens": 3})


def test_missing_usage_is_empty_dict(stub_llm):
    stub_llm.push({"choices": [{"message": {"content": json.dumps(OK)}}]})
    assert call() == (OK, {})


@pytest.mark.parametrize("text", [
    '好的，评审结果如下：\n{"dimensions": [], "redlines": []}\n以上。',
    '```json\n{"dimensions": [], "redlines": []}\n```',
    '{"dimensions": [], "redlines": []}  {"另一个": 1}',
])
def test_tolerates_text_around_json(stub_llm, text):
    stub_llm.push(completion(text))
    assert call()[0] == OK
    assert len(stub_llm.requests) == 1


def test_raw_control_chars_in_strings_allowed(stub_llm):
    stub_llm.push(completion('{"dimensions": [], "redlines": [], "summary": "第一行\n第二行\t制表"}'))
    assert call()[0]["summary"] == "第一行\n第二行\t制表"


def test_brace_in_preamble(stub_llm):
    stub_llm.push(completion('说明：分数用 {1-5} 表示。\n{"dimensions": [], "redlines": []}'))
    assert call()[0] == OK


@pytest.mark.parametrize("bad", ['{"dimensions": [{"id": "C1", "sco', "抱歉，无法完成。", ""])
def test_bad_json_retried_then_succeeds(stub_llm, bad):
    stub_llm.push(completion(bad))
    stub_llm.push(completion(OK))
    assert call()[0] == OK
    assert len(stub_llm.requests) == 2 and stub_llm.sleeps == [1]


def test_max_tokens_leaves_room_for_thinking(stub_llm):
    # B 层：成片关 20+ 帧时思考 4–8k + JSON 约 3k，8000 会截断
    stub_llm.push(completion(OK))
    call()
    assert stub_llm.requests[0]["body"]["max_tokens"] == vr.MAX_TOKENS >= 16000


def test_truncated_output_says_length(stub_llm, capsys):
    stub_llm.push({"choices": [{"message": {"content": '{"dimensions": [{"id": "V1", "evi'}, "finish_reason": "length"}]})
    stub_llm.push(completion(OK))
    assert call()[0] == OK
    assert "max_tokens" in capsys.readouterr().err


def test_unaccepted_param_dropped_and_retried(stub_llm):
    stub_llm.push({"error": {"message": "temperature is not supported for this model"}}, 400)
    stub_llm.push(completion(OK))
    assert call()[0] == OK
    assert "temperature" in stub_llm.requests[0]["body"] and "temperature" not in stub_llm.requests[1]["body"]


def test_persistent_bad_json_raises_after_retries(stub_llm):
    stub_llm.default = completion("不是 JSON")
    with pytest.raises(RuntimeError, match="连续失败"):
        call()
    assert len(stub_llm.requests) == 3


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_server_errors_retried(stub_llm, status):
    stub_llm.push({"error": "x"}, status)
    stub_llm.push(completion(OK))
    assert call()[0] == OK and len(stub_llm.requests) == 2


@pytest.mark.parametrize("status,body", [
    (401, {"error": "invalid key"}),
    (402, {"error": "payment"}),
    (400, {"error": {"message": "Insufficient Balance"}}),
])
def test_auth_and_balance_errors_stop_immediately(stub_llm, status, body):
    stub_llm.push(body, status)
    with pytest.raises(RuntimeError, match="鉴权或余额"):
        call()
    assert len(stub_llm.requests) == 1 and stub_llm.sleeps == []


def test_connection_refused_retried(monkeypatch):
    sleeps, attempts = [], []
    real = urllib.request.urlopen
    monkeypatch.setattr(vr.time, "sleep", sleeps.append)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: attempts.append(1) or real(*a, **k))
    with pytest.raises(RuntimeError, match="连续失败"):
        call()  # _no_network 把地址指向 127.0.0.1:9
    assert len(attempts) == 3
    assert sleeps == [1, 2]  # 指数退避，最后一次失败后不再等待


def test_no_sleep_after_last_attempt(stub_llm):
    stub_llm.default = completion("坏")
    with pytest.raises(RuntimeError):
        call()
    assert stub_llm.sleeps == [1, 2]


@pytest.mark.parametrize("bad", [{"choices": []}, {"choices": [{"message": {"content": None}}]}])
def test_malformed_envelope_is_retried(stub_llm, bad):
    stub_llm.push(bad)
    stub_llm.push(completion(OK))
    assert call()[0] == OK


@pytest.mark.parametrize("bad", [{"error": "奇怪的 200"}, {"choices": [{"message": {}}]}, completion([1, 2])])
def test_missing_keys_or_non_object_retried(stub_llm, bad):
    stub_llm.push(bad)
    stub_llm.push(completion(OK))
    assert call()[0] == OK


def test_read_timeout_is_retried(stub_llm, monkeypatch):
    real = urllib.request.urlopen
    n = {"i": 0}

    class Slow:
        def read(self):
            raise TimeoutError("The read operation timed out")

    def fake(*a, **k):
        n["i"] += 1
        return Slow() if n["i"] == 1 else real(*a, **k)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    stub_llm.push(completion(OK))
    assert call()[0] == OK


@pytest.fixture
def flaky_server(monkeypatch):
    """原始 TCP 服务：第一个连接按指定方式出故障，之后的连接返回正常响应。"""
    import socket
    import struct
    import threading

    good = json.dumps(completion(OK)).encode()
    state = {"mode": None, "n": 0}
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def read_request(c):
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += c.recv(65536)
        head, body = buf.split(b"\r\n\r\n", 1)
        n = int(next(l.split(b":")[1] for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")))
        while len(body) < n:
            body += c.recv(65536)

    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            with c:
                read_request(c)
                state["n"] += 1
                if state["n"] == 1 and state["mode"] == "close":
                    pass  # 不回任何字节直接关 → RemoteDisconnected
                elif state["n"] == 1 and state["mode"] == "reset":
                    c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))  # 发 RST
                elif state["n"] == 1 and state["mode"] == "short":
                    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              + f"Content-Length: {len(good)}\r\n\r\n".encode() + good[:10])
                else:
                    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                              + f"Content-Length: {len(good)}\r\nConnection: close\r\n\r\n".encode() + good)

    threading.Thread(target=serve, daemon=True).start()
    url = f"http://127.0.0.1:{srv.getsockname()[1]}/chat/completions"
    monkeypatch.setattr(vr, "api_url", lambda: url)
    monkeypatch.setattr(vr.time, "sleep", lambda s: None)
    yield state
    srv.close()


@pytest.mark.parametrize("mode", ["close", "reset", "short"])
def test_connection_errors_during_response_are_retried(flaky_server, mode):
    flaky_server["mode"] = mode
    assert call()[0] == OK
    assert flaky_server["n"] == 2


def test_flaky_server_control_case(flaky_server):
    # 对照：服务端不出故障时一次成功。保证上面的 xfail 是因为故障本身，而不是桩写错了
    assert call()[0] == OK and flaky_server["n"] == 1


@pytest.mark.parametrize("partial", [{"redlines": []}, {"dimensions": []}, {"summary": "只有总评"}])
def test_schema_incomplete_output_is_retried(stub_llm, partial):
    stub_llm.push(completion(partial))
    stub_llm.push(completion(OK))
    assert call()[0] == OK
