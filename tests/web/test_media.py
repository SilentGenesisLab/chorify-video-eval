"""C6 /media：根目录白名单、路径穿越、双重解码、Range、任务目录里哪些文件可见。"""
import pytest

import harness as h
from conftest import TOKEN

LABELS = "/media/dataset/labels.jsonl"


def get(site, path, **hd):
    return site.request("GET", path, headers={**h.bearer(TOKEN), **hd})


def test_dataset_file_served(site):
    r = get(site, LABELS)
    assert r.status == 200 and r.body.startswith(b"{") and r.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize("path", [
    "/media/../rubrics.json", "/media/dataset/../../rubrics.json", "/media/dataset/..%2f..%2frubrics.json",
    "/media/dataset/%2e%2e/%2e%2e/rubrics.json", "/media/dataset/%252e%252e/%252e%252e/rubrics.json",
    "/media/dataset/..%252f..%252frubrics.json", "/media/dataset/..%5c..%5crubrics.json",
    "/media/dataset/%2e%2e%5c%2e%2e%5c.env", "/media/dataset/..%255c..%255c.env",
    "/media/jobs/..%2f..%2f..%2fpackage.json", "/media/jobs/%252e%252e%252f%252e%252e%252fpackage.json",
    "/media/results/dev_v3/summary.json", "/media/.env", "/media/dataset/C:%5cWindows%5cwin.ini",
    "/media/dataset/%00", "/media/dataset", "/media/dataset/", "/media/jobs",
    # 和白名单根目录同级、名字以其开头的金丝雀目录：只按字符串前缀比较的实现会放行
    "/media/dataset-secret/secret.json", "/media/dataset/../dataset-secret/secret.json",
    "/media/dataset/..%2fdataset-secret%2fsecret.json", "/media/jobs-secret/secret.json",
    "/media/jobs/..%2fjobs-secret%2fsecret.json", "/media/jobs/%252e%252e%252fjobs-secret%252fsecret.json",
])
def test_traversal_blocked(site, path):
    r = get(site, path)
    # 308：Next 去掉末尾斜杠的规范化跳转，目标路径在本用例里另有一条
    ok = (400, 404, 308) if path.endswith("/") else (400, 404)
    assert r.status in ok, (path, r)
    assert h.CANARY_KEY.encode() not in r.body and b'"stages"' not in r.body


@pytest.mark.parametrize("path", ["/media/dataset/%25", "/media/dataset/%25zz", "/media/dataset/%25E4%25B8"])
def test_malformed_percent_is_404_not_500(site, path):
    # %25 → 路由层解成 %，代码再 decodeURIComponent 一次就抛 URIError
    assert get(site, path).status in (400, 404)


def test_double_encoding_does_not_reach_real_names(site):
    # %252E 只该解一次成字面量 %2E，不存在叫 labels%2Ejsonl 的文件
    assert get(site, "/media/dataset/labels%252Ejsonl").status == 404


def test_percent_in_uploaded_name_link_works(api, site):
    """接口返回的链接必须能打开：名字里带 % 的文件，链接里编码成 %25。"""
    r = api.submit({"title": "__crash__", "content": "", "files": [{"name": "50%off.md", "text": "折扣"}]})
    assert r.status == 202, r
    f = r.json()["inputs"]["files"][0]
    g = get(site, "/media/" + f["url"].split("/media/", 1)[1])
    assert g.status == 200 and g.body == "折扣".encode(), (f["url"], g)


@pytest.mark.parametrize("rng,status,start,end", [
    ("bytes=0-9", 206, 0, 9), ("bytes=10-", 206, 10, None), ("bytes=-10", 206, -10, None),
    ("bytes=0-0", 206, 0, 0),
])
def test_range_ok(site, rng, status, start, end):
    full = get(site, LABELS).body
    r = get(site, LABELS, Range=rng)
    want = full[start:None if end is None else end + 1]
    assert r.status == status and r.body == want
    assert r.headers["content-range"].endswith(f"/{len(full)}") and int(r.headers["content-length"]) == len(want)


@pytest.mark.parametrize("rng", ["bytes=999999999-", "bytes=5-2"])
def test_range_unsatisfiable(site, rng):
    n = len(get(site, LABELS).body)
    r = get(site, LABELS, Range=rng)
    assert r.status == 416 and r.headers["content-range"] == f"bytes */{n}"


@pytest.mark.parametrize("rng", ["bytes=0-999999999", "bytes=-999999999"])
def test_range_past_end_is_clamped(site, rng):
    full = get(site, LABELS).body
    r = get(site, LABELS, Range=rng)
    assert r.status == 206 and r.body == full


@pytest.mark.parametrize("rng", ["bytes=abc", "items=0-5", "bytes=", "bytes=-", "bytes=0-1,5-9"])
def test_range_garbage_does_not_crash(site, rng):
    assert get(site, LABELS, Range=rng).status in (200, 206, 416)


@pytest.mark.parametrize("rng", ["items=0-5", "bytes=abc", "bytes="])
def test_unrecognized_range_ignored(site, rng):
    """RFC 9110 §14.2：不认识的范围单位必须忽略；无效的 bytes 范围可以忽略（200）或拒绝（416），但不能回 206 + 全文。"""
    full = get(site, LABELS).body
    r = get(site, LABELS, Range=rng)
    assert (r.status == 200 and r.body == full) or (r.status == 416 and rng != "items=0-5"), r


def test_job_inputs_and_report_served(site, done_job):
    id = done_job["id"]
    assert get(site, f"/media/jobs/{id}/report.md").status == 200
    for f in done_job["inputs"]["files"]:
        assert get(site, "/media/" + f["url"].split("/media/", 1)[1]).status == 200, f


@pytest.mark.parametrize("name", ["job.json", "status.json", "log.txt"])
def test_job_internal_files_hidden(site, done_job, name):
    assert get(site, f"/media/jobs/{done_job['id']}/{name}").status == 404


def test_content_types(site, done_job):
    assert get(site, f"/media/jobs/{done_job['id']}/report.md").headers["content-type"].startswith("text/markdown")
    assert get(site, LABELS).headers["content-type"] == "application/octet-stream"
