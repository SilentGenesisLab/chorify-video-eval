"""C5 只读接口与页面、C8 OpenAPI 与实际路由一致、基准轮次接口（启动 / 409 / dry_run）。"""
import re
import time
from pathlib import Path

import pytest

import harness as h
from conftest import TOKEN

CASE = "S01_asset_as_blur"
ROUTES = Path(h.SITE_SRC) / "app" / "api" / "v1"


def test_rubrics(api):
    r = api("GET", "/api/v1/rubrics").json()
    assert set(r["stages"]) == {"creative", "storyboard", "asset", "video"} and "pass" in r["verdict_rules"]
    s = api("GET", "/api/v1/rubrics/video").json()
    assert "V1" in str(s)
    assert api("GET", "/api/v1/rubrics/nope").status == 404


def test_cases_list_filters_and_pagination(api):
    r = api("GET", "/api/v1/cases?split=dev").json()
    assert r["total"] == 105 and r["limit"] == 50 and len(r["items"]) == 50
    assert api("GET", "/api/v1/cases?split=dev&stage=asset").json()["total"] == 20
    assert api("GET", "/api/v1/cases?limit=99999").json()["limit"] == 500
    assert api("GET", "/api/v1/cases?split=dev&offset=100").json()["items"].__len__() == 5
    assert api("GET", "/api/v1/cases?q=as_blur").json()["total"] >= 1
    assert api("GET", "/api/v1/cases?split=dev&result=none").json()["total"] == 0  # dev_v3 覆盖了全部 dev 用例


def test_case_detail(api):
    c = api("GET", f"/api/v1/cases/{CASE}").json()
    assert c["id"] == CASE and c["evaluation"]["run"] == "dev_v3" and c["result"]
    assert all(f["url"].split("/media/", 1)[1].startswith("dataset/") for f in c["inputs"]["files"])
    assert api("GET", "/api/v1/cases/nope").status == 404
    assert api("GET", "/api/v1/cases/..%2f..%2frubrics").status == 404


def test_case_media_links_resolve(api, site):
    """图片 / 视频被 .gitignore 排除（build_dataset.py 重新生成），只核对本地真实存在的文件；中文文件名走 URL 编码。"""
    from urllib.parse import unquote
    c = api("GET", f"/api/v1/cases/{CASE}").json()
    checked = 0
    for f in c["inputs"]["files"] + c["inputs"]["context"]:
        rel = f["url"].split("/media/", 1)[1]
        exists = (site.root / "benchmark" / unquote(rel)).exists()
        assert api("GET", "/media/" + rel).status == (200 if exists else 404), f
        checked += exists
    assert checked >= 2


def test_benchmark_runs_read(api):
    names = [r["name"] for r in api("GET", "/api/v1/benchmark/runs").json()["items"]]
    assert "dev_v3" in names
    r = api("GET", "/api/v1/benchmark/runs/dev_v3?include=rows").json()
    assert r["status"] == "done" and r["summary"]["cases"] == 105 and len(r["summary"]["rows"]) == 105
    for bad in ("nope", "..%2fdataset", "a" * 41, "x%00"):
        assert api("GET", f"/api/v1/benchmark/runs/{bad}").status == 404, bad


@pytest.mark.parametrize("body,code", [
    ({"name": "bad name"}, "invalid_name"), ({"name": "../x"}, "invalid_name"), ({"name": "a" * 41}, "invalid_name"),
    ({"name": "ok", "split": "x"}, "invalid_split"), ({"name": "ok", "stages": ["nope"]}, "invalid_stage"),
    ({"name": "ok", "stages": "video"}, "invalid_body"), ({"name": "ok", "runs": 5}, "invalid_runs"),
    ({"name": "ok", "workers": 0}, "invalid_workers"), ({"name": "ok", "workers": 2.5}, "invalid_workers"),
    ({"name": "ok", "effort": "x"}, "invalid_effort"), ({"name": "ok", "scenarios": ["nope"]}, "no_cases"),
])
def test_benchmark_start_validation(api, body, code):
    r = api("POST", "/api/v1/benchmark/runs", body)
    assert r.status == 400 and r.json()["error"]["code"] == code, r


def test_benchmark_dry_run_estimate(api, site):
    r = api("POST", "/api/v1/benchmark/runs", {"name": "dev_v3", "split": "dev", "dry_run": True})
    assert r.status == 200 and r.json()["estimate"] == {"cases": 105, "cached": 105, "to_run": 0, "samples": 0,
                                                        "estimated_cost_cny": 0}
    e = api("POST", "/api/v1/benchmark/runs", {"name": "fresh", "split": "dev", "stages": ["asset"], "runs": 3,
                                                "dry_run": True}).json()["estimate"]
    assert e["to_run"] == 20 and e["samples"] == 60
    assert not (site.root / "benchmark" / "results" / "fresh").exists(), "dry_run 不应创建目录"


def test_benchmark_start_conflict_then_done(api, site):
    a, b = f"c_{time.time_ns()}", f"d_{time.time_ns()}"
    r = api("POST", "/api/v1/benchmark/runs", {"name": a, "split": "dev", "stages": ["asset"]})
    assert r.status == 202, r
    r2 = api("POST", "/api/v1/benchmark/runs", {"name": b, "split": "dev", "stages": ["asset"]})
    assert r2.status == 409 and r2.json()["error"]["running"] == a
    assert api("GET", f"/api/v1/benchmark/runs/{a}").json()["status"] == "running"
    assert h.wait_for(lambda: api("GET", f"/api/v1/benchmark/runs/{a}").json()["status"] == "done", 20)
    assert api("POST", "/api/v1/benchmark/runs", {"name": b, "split": "dev", "stages": ["asset"], "dry_run": True}).status == 200


def test_benchmark_bad_json(api):
    assert api("POST", "/api/v1/benchmark/runs", "{x", headers={"Content-Type": "application/json"}).status == 400


@pytest.mark.parametrize("ctype", ["text/plain", "application/x-www-form-urlencoded", None])
def test_benchmark_start_requires_json_content_type(api, ctype):
    """text/plain 与表单是浏览器跨站『简单请求』，不触发预检；dry_run 不启动进程，只看是否被解析。"""
    body = '{"name": "csrf", "split": "dev", "stages": ["asset"], "dry_run": true}'
    hd = {"Content-Type": ctype} if ctype else {}
    r = api("POST", "/api/v1/benchmark/runs", body.encode(), headers=hd)
    assert r.status == 415, r


@pytest.mark.parametrize("spec", [
    {}, {"split": "dev"}, {"split": "test", "stages": ["video"]}, {"stages": ["creative", "asset"]},
    {"scenarios": ["S02", "S05"]}, {"variants": ["base"]}, {"variants": ["base", "cr_infeasible"], "split": "test"},
    {"stages": ["storyboard"], "scenarios": ["S01"], "variants": ["base"]},
    {"stages": [], "scenarios": [], "variants": []},
], ids=lambda s: str(s) or "all")
def test_dry_run_matches_python_load_labels(api, spec):
    """估算用 JS 的 filterLabels，真正跑的是 Python 的 load_labels：两边筛出的用例数必须一致。"""
    from types import SimpleNamespace
    import run_benchmark as rb
    e = api("POST", "/api/v1/benchmark/runs", {"name": f"x{time.time_ns()}", "dry_run": True, **spec})
    assert e.status == 200, e
    py = rb.load_labels(SimpleNamespace(stages=spec.get("stages") or None, scenarios=spec.get("scenarios") or None,
                                        variants=spec.get("variants") or None, split=spec.get("split")))
    assert e.json()["estimate"]["cases"] == len(py)


def test_case_page_sanitizes_markdown(site):
    """数据集副本里的 .md 追加了原始 <img onerror> 和 javascript: 链接（harness.mini_root）。"""
    r = site.request("GET", f"/cases/{h.XSS_CASE}", headers=h.bearer(TOKEN))
    assert r.status == 200
    assert "onerror=" not in r.text and "javascript:window.__mdxss" not in r.text


def test_case_page_renders_markdown_control(site):
    """对照：页面确实渲染了这份材料，上一条不是因为材料没出现才通过。"""
    r = site.request("GET", f"/cases/{h.XSS_CASE}", headers=h.bearer(TOKEN))
    assert "creative.md" in r.text and "点我" in r.text


@pytest.mark.parametrize("path", ["/", "/rubric", "/framework", "/guide", "/docs", "/evaluate", "/jobs", "/benchmark",
                                  "/cases", f"/cases/{CASE}", "/cases?stage=video"])
def test_pages_render(site, path):
    r = site.request("GET", path, headers=h.bearer(TOKEN))
    assert r.status == 200 and "<html" in r.text, (path, r)


@pytest.mark.parametrize("path", ["/nope", "/cases/nope", "/jobs/nope", "/jobs/..%2f..%2fx"])
def test_unknown_pages_404(site, path):
    assert site.request("GET", path, headers=h.bearer(TOKEN)).status == 404


def test_health_does_not_leak_key(api):
    r = api("GET", "/api/v1/health")
    assert r.status == 200 and h.CANARY_KEY not in r.text and "sk-test" not in r.text


# ---------- C8 OpenAPI 与路由一致 ----------

def _routes():
    out = {}
    for f in ROUTES.rglob("route.js"):
        rel = f.parent.relative_to(ROUTES).as_posix()
        path = "/api/v1" + ("" if rel == "." else "/" + re.sub(r"\[(\w+)\]", r"{\1}", rel))
        out[path] = set(re.findall(r"export const (GET|POST|DELETE|PUT|PATCH)\b", f.read_text(encoding="utf-8")))
    return out


def test_openapi_matches_routes(api):
    spec = api("GET", "/api/v1/openapi.json").json()
    documented = {p: {m.upper() for m in ops} for p, ops in spec["paths"].items()}
    actual = _routes()
    actual.pop("/api/v1/openapi.json", None)
    # reviews/[id] 同时承载 GET/DELETE {id} 与 POST {stage}
    rid = actual.pop("/api/v1/reviews/{id}")
    actual["/api/v1/reviews/{id}"] = rid - {"POST"}
    actual["/api/v1/reviews/{stage}"] = {"POST"}
    assert documented == actual


def test_openapi_servers_use_request_host(api, site):
    spec = api("GET", "/api/v1/openapi.json").json()
    assert spec["servers"][0]["url"].startswith(f"http://127.0.0.1:{site.port}")


def test_documented_error_codes_exist():
    """API 文档里列出的错误码都在代码里真实存在（反之不要求：内部码可以不进文档）。"""
    src = "\n".join(p.read_text(encoding="utf-8") for p in (Path(h.SITE_SRC) / "lib").glob("*.js")) + \
        "\n".join(p.read_text(encoding="utf-8") for p in ROUTES.rglob("*.js"))
    used = set(re.findall(r'ApiError\(\d+, "([a-z_]+)"', src)) | {"unauthorized", "internal_error"}
    doc = (Path(h.SITE_SRC) / "docs" / "API文档.md").read_text(encoding="utf-8")
    section = doc.split("### 错误格式", 1)[1].split("\n### ", 1)[0]
    codes = set(re.findall(r"`([a-z]+_[a-z_]+)`", section))
    assert len(codes) >= 10 and codes <= used, codes - used


def test_all_raised_error_codes_are_documented():
    src = "\n".join(p.read_text(encoding="utf-8") for p in [*(Path(h.SITE_SRC) / "lib").glob("*.js"), *ROUTES.rglob("*.js")])
    used = set(re.findall(r'ApiError\(\d+, "([a-z_]+)"', src))
    doc = (Path(h.SITE_SRC) / "docs" / "API文档.md").read_text(encoding="utf-8")
    section = doc.split("### 错误格式", 1)[1].split("\n### ", 1)[0]
    assert used - {"not_found"} <= set(re.findall(r"`([a-z]+_[a-z_]+)`", section)) | {"not_found"}, \
        used - set(re.findall(r"`([a-z]+_[a-z_]+)`", section))
