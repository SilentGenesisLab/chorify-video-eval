"""C3/C4 任务：状态流转、排队与并发、删除、同步等待、回调、重启恢复、工作进程失败。"""
import time

import pytest

import harness as h
from conftest import TOKEN, Api


@pytest.fixture(scope="module")
def q(sites):
    return Api(sites("queue"))


def test_done_job_shape(done_job):
    j = done_job
    assert j["started_at"] and j["finished_at"] and j["elapsed_seconds"] is not None
    assert j["links"]["report"] and j["queue_position"] is None and j["error"] is None
    d = {x["id"]: x for x in j["result"]["dimensions"]}
    assert set(d) == {f"C{i}" for i in range(1, 9)} and all(x["score"] == 4 for x in d.values())


def test_redline_hit_rejects(api):
    j = api.wait(api.submit({"content": "__hit__"}).json()["id"])
    assert j["result"]["verdict"] == "驳回（命中红线）"
    assert j["result"]["redlines"][0]["status"] == "命中"


def test_queue_respects_max_running(q, sites):
    a = q.submit({"content": "__slow__ a"}).json()["id"]
    b = q.submit({"content": "__slow__ b"}).json()["id"]
    ja, jb = q("GET", f"/api/v1/reviews/{a}").json(), q("GET", f"/api/v1/reviews/{b}").json()
    assert ja["status"] == "running" and jb["status"] == "queued" and jb["queue_position"] == 1
    assert q("GET", "/api/v1/health").json()["queue"] == {"running": 1, "queued": 1, "max_running": 1}
    assert q.wait(a)["status"] == "done" and q.wait(b)["status"] == "done"


def test_delete_rules(q):
    a = q.submit({"content": "__slow__ del-a"}).json()["id"]
    b = q.submit({"content": "__slow__ del-b"}).json()["id"]
    assert q("DELETE", f"/api/v1/reviews/{a}").json()["error"]["code"] == "job_running"
    assert q("DELETE", f"/api/v1/reviews/{b}").status == 204
    assert q("GET", f"/api/v1/reviews/{b}").status == 404
    assert q.wait(a)["status"] == "done"
    assert q("GET", "/api/v1/health").json()["queue"]["queued"] == 0, "删掉的排队任务仍在队列里"
    assert q("DELETE", f"/api/v1/reviews/{a}").status == 204
    assert q("DELETE", f"/api/v1/reviews/{a}").status == 404


@pytest.mark.parametrize("id", ["nope", "20260101-00000000", "..", "..%2f..%2fdata", "A-UPPER", "%2e%2e"])
def test_unknown_ids_404(api, id):
    for m in ("GET", "DELETE"):
        assert api(m, f"/api/v1/reviews/{id}").status == 404
    assert api("GET", f"/api/v1/reviews/{id}/report").status == 404


def test_report_not_ready_then_ready(q):
    a = q.submit({"content": "__slow__ report"}).json()["id"]
    r = q("GET", f"/api/v1/reviews/{a}/report")
    assert r.status == 409 and r.json()["error"]["code"] == "not_ready"
    q.wait(a)
    r = q("GET", f"/api/v1/reviews/{a}/report")
    assert r.status == 200 and r.headers["content-type"].startswith("text/markdown") and "创意" in r.text


def test_raw_runs_only_on_request(api, done_job):
    id = done_job["id"]
    assert "raw_runs" not in api("GET", f"/api/v1/reviews/{id}").json()["result"]
    assert len(api("GET", f"/api/v1/reviews/{id}?include=raw_runs").json()["result"]["raw_runs"]) == 1


@pytest.mark.parametrize("where", ["body", "query"])
def test_wait_returns_finished_job(api, where):
    body = {"wait": 30} if where == "body" else {}
    r = api("POST", "/api/v1/reviews" + ("?wait=30" if where == "query" else ""),
            {"stage": "creative", "content": "wait", "runs": 1, **body})
    assert r.status == 200 and r.json()["status"] == "done", r


@pytest.mark.parametrize("wait", [-5, "abc", 0])
def test_wait_invalid_values_do_not_block(api, wait):
    t = time.time()
    r = api.submit({"wait": wait, "content": "__slow__ nowait"})
    assert r.status == 202 and time.time() - t < 3


def test_wait_times_out_with_202(q):
    t = time.time()
    r = q.submit({"wait": 1, "content": "__slow__ waitto"})
    assert r.status == 202 and 1 <= time.time() - t < 6
    q.wait(r.json()["id"])


def test_callback_delivered(api, helper):
    # helper 在 SSRF_ALLOW_HOSTS 里（conftest），B46 修复后这条照常能跑
    cb = helper.url(f"/cb/{time.time_ns()}")
    j = api.wait(api.submit({"callback_url": cb}).json()["id"])
    got = h.wait_for(lambda: [c for c in helper.callbacks if c["path"] == cb.split(str(helper.port))[1]], 15)
    assert got and got[0]["body"]["id"] == j["id"] and got[0]["body"]["status"] == "done"
    assert got[0]["body"]["result"]["verdict"] == "通过"


def test_callback_on_error(api, helper):
    cb = helper.url(f"/cb/err{time.time_ns()}")
    j = api.wait(api.submit({"callback_url": cb, "content": "__402__"}).json()["id"])
    got = h.wait_for(lambda: [c for c in helper.callbacks if c["path"].endswith(cb.rsplit("/", 1)[1])], 15)
    assert got and got[0]["body"]["status"] == "error" == j["status"]


def test_callback_failure_retried_and_logged(api, site):
    j = api.wait(api.submit({"callback_url": "http://127.0.0.1:9/cb"}).json()["id"])
    log = site.jobs / j["id"] / "log.txt"
    assert h.wait_for(lambda: log.read_text(encoding="utf-8").count("[callback]") >= 3, 20), log.read_text(encoding="utf-8")


def test_model_402_is_error(api):
    j = api.wait(api.submit({"content": "__402__"}).json()["id"])
    assert j["status"] == "error" and "余额" in j["error"] and j["result"] is None


def test_worker_crash_is_error(api):
    j = api.wait(api.submit({"title": "__crash__"}).json()["id"])
    assert j["status"] == "error" and "（3）" in j["error"] and "simulated crash" in j["error"]


def test_missing_python_is_error_and_queue_freed(sites):
    s = sites("nopython")
    a = Api(s)
    r = a.submit()
    assert r.status == 202
    j = h.wait_for(lambda: (x := a("GET", f"/api/v1/reviews/{r.json()['id']}").json())["status"] == "error" and x, 10)
    assert j, "PYTHON 不存在时任务没有转为 error"
    assert a("GET", "/api/v1/health").json()["queue"]["running"] == 0


def test_missing_python_does_not_kill_server(sites):
    s = sites("nopython")
    Api(s).submit()
    time.sleep(1)
    assert s.proc.poll() is None and Api(s)("GET", "/api/v1/rubrics").status == 200


def test_restart_marks_inflight_jobs_as_error(build_dir, stub):
    env = {"SITE_API_TOKEN": TOKEN, "MAX_RUNNING": "1"}
    s = h.Site(build_dir, env, stub.url("/chat/completions"), name="restart").start()
    a = Api(s)
    run, queued = a.submit({"content": "__slow__ r1"}).json()["id"], a.submit({"content": "__slow__ r2"}).json()["id"]
    s.stop()
    s2 = h.Site(build_dir, env, stub.url("/chat/completions"), home=s.home).start()
    try:
        for id in (run, queued):
            j = Api(s2)("GET", f"/api/v1/reviews/{id}").json()
            assert j["status"] == "error" and "重启" in j["error"], j
        assert Api(s2)("GET", "/api/v1/health").json()["queue"] == {"running": 0, "queued": 0, "max_running": 1}
    finally:
        s2.stop()


def test_list_filters_and_pagination(api, done_job):
    r = api("GET", "/api/v1/reviews?status=done&stage=creative&limit=2").json()
    assert r["limit"] == 2 and len(r["items"]) <= 2 and all(i["status"] == "done" for i in r["items"])
    assert all("result" not in i and "inputs" not in i and "verdict" in i for i in r["items"])
    assert api("GET", "/api/v1/reviews?status=bogus").json()["error"]["code"] == "invalid_status"
    assert api("GET", "/api/v1/reviews?limit=99999").json()["limit"] == 200
    assert api("GET", "/api/v1/reviews?limit=-3&offset=-1").json()["offset"] == 0
    created = [i["created_at"] for i in api("GET", "/api/v1/reviews?limit=200").json()["items"]]
    assert created == sorted(created, reverse=True)


def test_model_output_is_escaped_on_job_page(api, site):
    j = api.wait(api.submit({"content": "__xss__", "title": "<script>alert(1)</script>"}).json()["id"])
    page = site.request("GET", f"/jobs/{j['id']}", headers=h.bearer(TOKEN)).text
    assert "<img src=x onerror" not in page and "<script>window.__xss" not in page and "<script>alert(1)" not in page
    assert "&lt;img src=x onerror" in page or "&lt;img" in page
