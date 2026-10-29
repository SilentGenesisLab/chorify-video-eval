"""C2 提交校验：每条校验规则的接受 / 拒绝边界、错误码、落盘的文件名与参数。"""
import base64

import pytest

import harness as h

B64 = lambda b: base64.b64encode(b).decode()
MP4 = {"name": "a.mp4", "content_base64": B64(b"\0\0\0\x18ftypmp42")}


def err(r):
    return r.status, (r.json().get("error") or {}).get("code")


@pytest.mark.parametrize("body,status,code", [
    ({"stage": "nope"}, 400, "invalid_stage"),
    ({"stage": None}, 400, "invalid_stage"),
    ({"content": ""}, 400, "missing_input"),
    ({"content": "   \n "}, 400, "missing_input"),
    ({"files": [{"name": "a.exe", "content_base64": "AA=="}]}, 400, "unsupported_file"),
    ({"files": [{"name": "noext", "content_base64": "AA=="}]}, 400, "unsupported_file"),
    ({"files": [{"name": "a.md.exe", "text": "x"}]}, 400, "unsupported_file"),
    ({"context_files": [{"name": "c.html", "text": "x"}]}, 400, "unsupported_file"),
    ({"files": [{"content_base64": "AA=="}]}, 400, "invalid_body"),
    ({"files": [{"name": "a.png"}]}, 400, "invalid_body"),
    ({"files": "a.png"}, 400, "invalid_body"),
    ({"context_files": {"name": "x"}}, 400, "invalid_body"),
    ({"files": [MP4]}, 400, "unexpected_video"),
    ({"stage": "video", "content": "只有文字"}, 400, "missing_video"),
    ({"stage": "video", "files": [{"name": "a.srt", "text": "1"}]}, 400, "missing_video"),
    ({"runs": 0}, 400, "invalid_runs"),
    ({"runs": 4}, 400, "invalid_runs"),
    ({"runs": 1.5}, 400, "invalid_runs"),
    ({"runs": "abc"}, 400, "invalid_runs"),
    ({"effort": "medium"}, 400, "invalid_effort"),
    ({"callback_url": "ftp://x/y"}, 400, "invalid_callback_url"),
    ({"callback_url": "javascript:alert(1)"}, 400, "invalid_callback_url"),
    ({"callback_url": "http://a b/"}, 400, "invalid_callback_url"),
    ({"files": [{"name": "a.png", "url": "file:///etc/passwd"}]}, 400, "invalid_file_url"),
    ({"files": [{"name": "a.png", "url": "gopher://127.0.0.1/"}]}, 400, "invalid_file_url"),
])
def test_rejections(api, body, status, code):
    assert err(api.submit(body)) == (status, code)


@pytest.mark.parametrize("runs", [1, 2, 3, "2", None, ""])
def test_runs_accepted(api, runs):
    r = api.submit({"runs": runs, "title": "__crash__"})
    assert r.status == 202, r
    assert r.json()["params"]["runs"] == (3 if runs in (None, "") else int(runs))


@pytest.mark.parametrize("effort", ["low", "high", "max", None])
def test_effort_accepted(api, effort):
    r = api.submit({"effort": effort, "title": "__crash__"})
    assert r.status == 202 and r.json()["params"]["effort"] == (effort or "high")


def test_content_type(api):
    assert err(api("POST", "/api/v1/reviews", "stage=creative", headers={"Content-Type": "text/plain"})) == \
        (415, "unsupported_media_type")
    assert err(api("POST", "/api/v1/reviews", "{bad json", headers={"Content-Type": "application/json"})) == \
        (400, "invalid_body")


@pytest.mark.parametrize("path,status", [
    ("/api/v1/reviews/creative", 202), ("/api/v1/reviews/storyboard", 202), ("/api/v1/reviews?stage=asset", 202),
    ("/api/v1/reviews/nope", 404), ("/api/v1/reviews/..%2fcreative", 404),
])
def test_stage_from_path_or_query(api, path, status):
    r = api("POST", path, {"content": "x", "runs": 1, "title": "__crash__"})
    assert r.status == status, r


def test_path_stage_overrides_body(api):
    r = api("POST", "/api/v1/reviews/storyboard", {"stage": "creative", "content": "x", "runs": 1, "title": "__crash__"})
    assert r.json()["stage"] == "storyboard"


def test_saved_names_are_sanitized(api, site):
    r = api.submit({"title": "__crash__", "content": "", "files": [
        {"name": "../../../evil.md", "text": "a"}, {"name": "..\\..\\win.md", "text": "b"},
        {"name": "a b:c*?.MD", "text": "c"}, {"name": "x" * 300 + ".md", "text": "d"}]})
    assert r.status == 202, r
    d = site.jobs / r.json()["id"] / "inputs"
    saved = list(d.rglob("*"))
    assert all(p.parent == d and p.is_file() for p in saved), saved  # 全部落在 inputs/ 里，没有子目录、没有穿越
    assert len(saved) == 4 and all(len(p.name) <= 70 for p in saved), [p.name for p in saved]
    assert not list(site.jobs.parent.rglob("evil.md")) and not list(site.jobs.parent.rglob("win.md"))


def test_title_default_and_truncation(api):
    assert api.submit({"title": "长" * 200}).json()["title"] == "长" * 80
    assert api.submit({"files": [{"name": "kv.md", "text": "x"}], "content": ""}).json()["title"] == "kv.md"
    assert api.submit({}).json()["title"] == "文本内容"


def test_srt_becomes_transcript_for_video(api):
    r = api.submit({"stage": "video", "title": "__crash__", "content": "", "files": [MP4, {"name": "sub.srt", "text": "1\n00:00 --> 00:01\n台词"}]})
    j = r.json()
    assert j["inputs"]["transcript"]["name"].endswith("sub.srt")
    assert [f["name"] for f in j["inputs"]["files"]] == ["01_a.mp4"]


def test_multipart_submission(api, site):
    body, ctype = h.multipart([("stage", None, b"storyboard"), ("runs", None, b"1"), ("title", None, b"__crash__"),
                               ("files", "分镜.md", "镜头 1".encode()), ("context", "brief.txt", b"brief")])
    r = api("POST", "/api/v1/reviews", body, headers={"Content-Type": ctype})
    assert r.status == 202, r
    j = r.json()
    assert j["stage"] == "storyboard" and len(j["inputs"]["files"]) == 1 and len(j["inputs"]["context"]) == 1


def test_multipart_garbage(api):
    r = api("POST", "/api/v1/reviews", b"--x\r\nnot a form", headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert err(r) == (400, "invalid_body")


def test_too_large_files(api):
    r = api.submit({"title": "__crash__", "files": [{"name": "big.md", "content_base64": B64(b"a" * (150 * 1024 * 1024 + 1))}]},
                   timeout=180)
    assert err(r) == (413, "too_large")


def test_exactly_150mb_accepted(api):
    r = api.submit({"title": "__crash__", "files": [{"name": "big.md", "content_base64": B64(b"a" * (150 * 1024 * 1024))}]},
                   timeout=180)
    assert r.status == 202, r


def test_content_text_counts_toward_limit(api):
    r = api.submit({"title": "__crash__", "content": "a" * (151 * 1024 * 1024)}, timeout=180)
    assert r.status == 413, r


def test_json_body_cap(api):
    # 230MB 的 JSON，有效字段很小：上限必须在读入请求体前生效
    body = b'{"stage":"creative","content":"x","runs":1,"title":"__crash__","pad":"' + b"a" * (230 * 1024 * 1024) + b'"}'
    r = api("POST", "/api/v1/reviews", body, headers={"Content-Type": "application/json"}, timeout=180)
    assert r.status == 413, r


@pytest.mark.parametrize("body", [{"content": 123}, {"title": 5}, {"callback_url": 1}, {"platform_hint": []}])
def test_wrong_field_types_are_400(api, body):
    assert api.submit({**body}).status == 400


def test_empty_object_body_is_invalid_stage(api):
    r = api("POST", "/api/v1/reviews", "{}", headers={"Content-Type": "application/json"})
    assert err(r) == (400, "invalid_stage")


@pytest.mark.parametrize("raw", ["[]", "1", '"s"', "true"])
def test_non_object_json_body_is_invalid_body(api, raw):
    # 现状是因为缺 stage 才报 400：错误码说的是另一回事
    r = api("POST", "/api/v1/reviews", raw, headers={"Content-Type": "application/json"})
    assert err(r) == (400, "invalid_body")


def test_base64_roundtrip_exact_bytes(api, site):
    data = bytes(range(256)) * 3
    r = api.submit({"title": "__crash__", "content": "", "files": [{"name": "kv.png", "content_base64": B64(data)}]})
    assert r.status == 202, r
    assert [p.read_bytes() for p in (site.jobs / r.json()["id"] / "inputs").iterdir()] == [data]


@pytest.mark.parametrize("b64", ["iVBO!!!Rw0KGgo=", "iVBORw0KGgo=@@@", "不是base64", "data:image/png;base64,iVBORw0KGgo="])
def test_invalid_base64_rejected(api, b64):
    r = api.submit({"title": "__crash__", "content": "", "files": [{"name": "kv.png", "content_base64": b64}]})
    assert err(r) == (400, "invalid_body")


def test_multipart_too_large(api):
    """multipart 文件合计超过 150MB：和 JSON 一样报 413。"""
    body, ctype = h.multipart([("stage", None, b"creative"), ("runs", None, b"1"), ("title", None, b"__crash__"),
                               ("files", "big.md", b"a" * (150 * 1024 * 1024 + 1))])
    r = api("POST", "/api/v1/reviews", body, headers={"Content-Type": ctype}, timeout=180)
    assert err(r) == (413, "too_large")


def test_submission_burst_is_rate_limited(sites):
    """同一凭据 1 秒内提交 30 个评审（每个默认 runs=3、调用付费模型）：应出现 429。
    用独立实例 burst，不影响其他实例的队列；__crash__ 让工作进程立刻退出，不调用模型。"""
    from conftest import Api
    a = Api(sites("burst"))
    codes = [a.submit({"title": "__crash__"}).status for _ in range(30)]
    assert 429 in codes, codes


def test_null_json_body_is_400(api):
    r = api("POST", "/api/v1/reviews", "null", headers={"Content-Type": "application/json"})
    assert r.status == 400, r


def test_location_header_and_202(api):
    r = api.submit({"title": "__crash__"})
    assert r.status == 202 and r.headers["location"] == r.json()["links"]["self"]
    assert r.json()["status"] in ("queued", "running")
