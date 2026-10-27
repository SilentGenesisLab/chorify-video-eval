# 视频评审台 API 文档

版本 v1 · 基础地址 `{{BASE_URL}}/api/v1`

本接口提供视频广告四道关卡的自动评审：**G1 创意（creative）→ G2 分镜（storyboard）→ G3 资产（asset）→ G4 成片（video）**。同时提供评分标准查询、评审器基准测试和用例库查询。

- 评审由 deepseek-flash 完成，每道关卡先查红线，再按维度打 1–5 分。
- 结论由服务端按固定规则计算，不由模型直接给出。
- 成片的响度、黑场、冻结帧、分辨率等技术指标由程序测量。

机器可读的 OpenAPI 3.0 规范：`GET /api/v1/openapi.json`，可直接导入 Postman、Apifox 或 Swagger UI。

## 概述

### 接口一览

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 评审 | POST | `/reviews/{stage}` | 提交评审任务 |
| 评审 | POST | `/reviews` | 提交评审任务（关卡写在请求体） |
| 评审 | GET | `/reviews/{id}` | 查询任务状态与结果 |
| 评审 | GET | `/reviews` | 任务列表 |
| 评审 | GET | `/reviews/{id}/report` | 下载 Markdown 评审报告 |
| 评审 | DELETE | `/reviews/{id}` | 删除任务 |
| 评分标准 | GET | `/rubrics` | 全部关卡的评分标准 |
| 评分标准 | GET | `/rubrics/{stage}` | 单个关卡的评分标准 |
| 基准测试 | GET | `/benchmark/runs` | 评测轮次列表 |
| 基准测试 | GET | `/benchmark/runs/{run}` | 轮次详情与指标 |
| 基准测试 | POST | `/benchmark/runs` | 发起评测轮次（或预估费用） |
| 用例库 | GET | `/cases` | 用例列表（可筛选） |
| 用例库 | GET | `/cases/{id}` | 用例详情：标准答案、材料、评审器判断 |
| 系统 | GET | `/health` | 健康检查、队列、账户余额 |
| 系统 | GET | `/openapi.json` | OpenAPI 规范 |

### 鉴权

所有接口都需要 API Token，下面两种请求头任选一种：

```http
Authorization: Bearer <API Token>
X-API-Key: <API Token>
```

Token 由管理员发放，保存在服务器 `review-site/.env.local` 的 `SITE_API_TOKEN` 中，修改后需重启服务。网页登录用的 Basic Auth（任意用户名 + 站点密码）对接口同样有效。

未授权时返回：

```json
HTTP/1.1 401
{ "error": { "code": "unauthorized", "message": "缺少或错误的 API Token，请在请求头加 Authorization: Bearer <token>" } }
```

### 请求与响应格式

- 请求体使用 `application/json` 或 `multipart/form-data`（上传文件时）。
- 响应统一为 JSON，UTF-8 编码；唯一例外是 Markdown 报告接口。
- 时间字段为 ISO 8601 UTC 格式，如 `2026-10-21T16:41:02.118Z`。
- 列表接口用 `limit` 和 `offset` 分页，返回 `total`。

### 错误格式

```json
{ "error": { "code": "missing_video", "message": "成片评审需要一个视频文件（mp4/mov/webm/m4v/mkv）" } }
```

| HTTP | code | 含义 |
|---|---|---|
| 400 | `invalid_stage` | stage 不是 creative / storyboard / asset / video |
| 400 | `missing_input` | 既没有 files 也没有 content |
| 400 | `missing_video` | 成片评审没有视频文件 |
| 400 | `unexpected_video` | 视频文件提交到了非 video 关卡 |
| 400 | `unsupported_file` | 文件扩展名不支持 |
| 400 | `invalid_runs` / `invalid_mode` / `invalid_effort` / `invalid_callback_url` | 参数取值错误 |
| 400 | `invalid_body` | JSON 格式错误或字段类型不对 |
| 400 | `file_download_failed` | 按 url 下载文件失败 |
| 400 | `invalid_name` / `invalid_split` / `invalid_workers` / `no_cases` | 基准测试参数错误 |
| 401 | `unauthorized` | 缺少或错误的 Token |
| 404 | `not_found` | 任务、关卡、轮次或用例不存在 |
| 409 | `not_ready` | 评审未完成，报告尚未生成 |
| 409 | `job_running` | 评审中的任务不能删除 |
| 409 | `run_in_progress` | 已有基准测试轮次在运行 |
| 413 | `too_large` | 文件合计超过 150MB |
| 415 | `unsupported_media_type` | Content-Type 不是 JSON 或 multipart |
| 500 | `internal_error` | 服务内部错误 |

### 限制

| 项目 | 限制 |
|---|---|
| 单次提交的文件合计 | 150MB |
| 支持的文件类型 | 文本 `.md .txt .csv .srt .json`；图片 `.png .jpg .jpeg .webp .gif`；视频 `.mp4 .mov .webm .m4v .mkv` |
| 并发评审 | 同时最多 2 个任务，其余排队（按提交顺序） |
| 同步等待 `wait` | 最长 300 秒 |
| 基准测试 | 同一时间只允许 1 个轮次运行 |

## 快速开始

### 第一步：提交评审，同步等待结果

```bash
TOKEN=<你的 API Token>
curl -X POST {{BASE_URL}}/api/v1/reviews/creative \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "轻氧 15s 抖音 创意 v2",
    "content": "【创意提案】……（创意全文）",
    "context": "【Brief】品牌：轻氧；产品：0 糖气泡水；目标人群：25–35 岁办公室白领……",
    "wait": 180
  }'
```

`wait` 期间评审完成，返回 200 和完整结果；超时则返回 202，结果需要用任务号查询。

### 第二步（可选）：异步查询

```bash
curl {{BASE_URL}}/api/v1/reviews/20261021-6f38ae71 -H "Authorization: Bearer $TOKEN"
```

当 `status` 为 `done` 时，`result` 字段包含完整结果。

### 第三步（可选）：下载可读报告

```bash
curl {{BASE_URL}}/api/v1/reviews/20261021-6f38ae71/report -H "Authorization: Bearer $TOKEN" -o report.md
```

## 评审

### 提交评审

```http
POST /api/v1/reviews/{stage}
POST /api/v1/reviews            （stage 写在请求体）
```

评审是异步的：

- **不传 `wait`**：服务端返回 **202** 和任务对象，`status` 为 `queued` 或 `running`，并在 `Location` 头中给出查询地址。
- **传 `wait`（秒）**：服务端在这段时间内等待评审完成。完成时返回 **200** 和完整结果，超时仍返回 202。

单次采样通常需要 30–90 秒。默认 3 次采样并发执行，总耗时与单次采样接近。成片评审还要先抽帧和测量响度，时间会更长。

#### 各关卡应提交什么

参考材料是前序关卡已经通过的内容，评审器用它对照“还原度”类维度。不提供参考材料时，这些维度只能凭空判断，分数会偏向中间。

| stage | 待评审材料（content / files） | 参考材料（context / context_files） |
|---|---|---|
| `creative` | 创意提案文本 | brief、品牌规范 |
| `storyboard` | 分镜表文本（可附草图图片） | 已通过的创意提案 |
| `asset` | 主视觉、角色设定、落版等图片 + 资产清单（写明字体、音乐、肖像的授权情况） | 分镜表 + 品牌规范 |
| `video` | 1 个视频文件；字幕 `.srt` 可放在 files 中，会自动作为台词 | 分镜表 |

#### JSON 请求体

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `stage` | string | 仅 `POST /reviews` 时必填 | `creative` / `storyboard` / `asset` / `video` |
| `content` | string 或 string[] | 与 `files` 至少一个 | 待评审文本，如创意提案、分镜表；数组会用空行拼接 |
| `files` | FileRef[] | 与 `content` 至少一个 | 待评审文件 |
| `context` | string 或 string[] | 否 | 参考材料文本 |
| `context_files` | FileRef[] | 否 | 参考材料文件 |
| `transcript` | string | 否 | 成片的台词或字幕。模型听不到声音，口播内容请写在这里 |
| `platform_hint` | string | 否 | 投放平台与规格。默认“短视频信息流（抖音/视频号），竖屏 9:16 1080x1920，响度 -14～-16 LUFS，真峰值 ≤ -1 dBTP” |
| `runs` | integer | 否 | 采样次数，取 1–3，默认 3。多次采样时维度分取均值，红线按多数票判定。`panel` 模式下是每位评审员的采样次数 |
| `mode` | string | 否 | `sample`（默认）：一位评审员按整套标准评 `runs` 次。`panel`：分维度评审团，`rubrics.json` 里该关卡的每位评审员只评自己负责的维度，另有一位合规评审员只判红线，彼此看不到对方的结论，并发执行；结果里多一个 `panels` 字段列出编制。结论计算规则两种模式相同 |
| `effort` | string | 否 | 推理强度：`low` / `high` / `max`，默认 `high` |
| `title` | string | 否 | 任务名称，最长 80 字 |
| `callback_url` | string | 否 | 任务完成或失败后，服务端向该地址 POST 任务对象 |
| `wait` | integer | 否 | 同步等待秒数，取 0–300，默认 0 |

**FileRef** 表示一个文件，下面三种写法任选一种：

```json
{ "name": "产品主视觉KV.png", "content_base64": "iVBORw0KGgo..." }
{ "name": "资产清单.md", "text": "| 资产 | 来源 | 授权 |\n|---|---|---|\n..." }
{ "name": "final.mp4", "url": "https://cdn.example.com/ads/final.mp4" }
```

- `name` 必须带扩展名，服务端按扩展名决定把文件当作文本、图片还是视频处理。
- 用 `url` 时由服务端下载文件，下载超时为 120 秒。

#### multipart/form-data

上传本地文件，尤其是视频时，用 multipart 更合适。字段名与 JSON 对应：

| 字段 | 说明 |
|---|---|
| `files` | 待评审文件，可重复多次 |
| `context` | 参考材料文件，可重复多次 |
| `content` | 待评审文本 |
| `context_text` | 参考材料文本 |
| `transcript`、`platform_hint`、`runs`、`mode`、`effort`、`title`、`callback_url`、`wait` | 同 JSON |
| `stage` | 仅 `POST /reviews` 时需要 |

#### 示例：分镜评审（JSON）

```bash
curl -X POST {{BASE_URL}}/api/v1/reviews/storyboard \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @- <<'EOF'
{
  "title": "字跃 30s 视频号 分镜 v1",
  "content": "| 镜号 | 时长 | 景别 | 运镜 | 画面 | 台词/字幕 | 音效 |\n|---|---|---|---|---|---|---|\n| 1 | 2s | 近景 | 快推 | …… | …… | …… |",
  "context": "（已通过的创意提案全文）",
  "runs": 3
}
EOF
```

#### 示例：资产评审（multipart，上传图片）

```bash
curl -X POST {{BASE_URL}}/api/v1/reviews/asset \
  -H "Authorization: Bearer $TOKEN" \
  -F title="远岚 S7 资产 v1" \
  -F files=@产品主视觉KV.png -F files=@角色设定_正面.png -F files=@片尾落版.png \
  -F files=@资产清单.md \
  -F context=@分镜.md -F context=@品牌规范.md
```

#### 示例：成片评审（multipart，上传视频 + 回调）

```bash
curl -X POST {{BASE_URL}}/api/v1/reviews/video \
  -H "Authorization: Bearer $TOKEN" \
  -F files=@final.mp4 -F files=@subtitles.srt \
  -F context=@分镜.md \
  -F platform_hint="B站横屏 16:9 1920x1080，响度 -16 LUFS" \
  -F callback_url="https://your-system.example.com/hooks/video-review"
```

#### 示例：Python

```python
import requests

BASE = "{{BASE_URL}}/api/v1"
H = {"Authorization": "Bearer <API Token>"}

# 提交成片评审
with open("final.mp4", "rb") as v, open("分镜.md", "rb") as sb:
    r = requests.post(f"{BASE}/reviews/video", headers=H,
                      files=[("files", v), ("context", sb)],
                      data={"transcript": "（口播全文）", "runs": 3})
job = r.json()

# 轮询结果
import time
while job["status"] in ("queued", "running"):
    time.sleep(5)
    job = requests.get(job["links"]["self"], headers=H).json()

if job["status"] == "done":
    res = job["result"]
    print(res["verdict"], res["total"])
    for x in res["redlines"]:
        if x["status"] != "未命中":
            print(x["id"], x["status"], x["evidence"])
else:
    print("失败：", job["error"])
```

### 查询评审任务

```http
GET /api/v1/reviews/{id}
GET /api/v1/reviews/{id}?include=raw_runs     附带每次采样的模型原始输出
```

返回 [任务对象](#任务对象-review)。

### 任务列表

```http
GET /api/v1/reviews?stage=video&status=done&limit=20&offset=0
```

| 参数 | 说明 |
|---|---|
| `stage` | 按关卡筛选 |
| `status` | `queued` / `running` / `done` / `error` |
| `limit` | 每页条数，默认 20，最大 200 |
| `offset` | 偏移量 |

按提交时间倒序返回。列表项不含 `inputs` 和 `result`，另外增加 `verdict` 和 `total` 两个字段。

```json
{
  "total": 37, "limit": 20, "offset": 0,
  "items": [
    { "id": "20261021-4543cb81", "stage": "creative", "title": "A·饭后那一口清·策划", "status": "done",
      "verdict": "修改后通过", "total": 3.6, "created_at": "2026-10-21T15:59:12.827Z", "elapsed_seconds": 51,
      "links": { "self": "…/api/v1/reviews/20261021-4543cb81", "report": "…/report", "web": "…/jobs/20261021-4543cb81" } }
  ]
}
```

### 下载 Markdown 报告

```http
GET /api/v1/reviews/{id}/report
```

返回 `text/markdown`。报告包含结论、技术参数、红线表、维度评分、优先修改项，以及每个维度的证据和建议，适合直接发给创作团队。任务未完成时返回 409 `not_ready`。

### 删除评审任务

```http
DELETE /api/v1/reviews/{id}
```

删除任务及其上传的文件，成功时返回 204。

- 排队中的任务会被取消。
- 评审中的任务不能删除，会返回 409 `job_running`。

### 完成回调

提交时如果带了 `callback_url`，任务结束后（`done` 或 `error`），服务端会向该地址发送一次请求：

- 方法为 `POST`，`Content-Type: application/json`，请求体是完整的[任务对象](#任务对象-review)，与 `GET /reviews/{id}` 的返回相同。
- 对方返回 2xx 视为送达；否则在 2、4、8 秒后各重试一次，共 3 次，每次超时 10 秒。
- 每次送达结果都会写入任务日志。

回调请求不带签名，请在 `callback_url` 中放一段只有你自己知道的随机路径或参数，例如 `https://your-system/hooks/review?secret=xxxx`，用来校验来源。

## 数据结构

### 任务对象（Review）

```json
{
  "id": "20261021-6f38ae71",
  "stage": "creative",
  "title": "S07 绵柔星 创意",
  "status": "done",
  "error": null,
  "queue_position": null,
  "created_at": "2026-10-21T16:40:28.004Z",
  "started_at": "2026-10-21T16:40:28.006Z",
  "finished_at": "2026-10-21T16:41:02.118Z",
  "elapsed_seconds": 34,
  "params": { "runs": 3, "effort": "high", "platform_hint": null, "callback_url": null },
  "inputs": {
    "files": [{ "name": "00_content.md", "url": "{{BASE_URL}}/media/jobs/20261021-6f38ae71/inputs/00_content.md" }],
    "context": [],
    "transcript": null
  },
  "result": {
    "verdict": "驳回（命中红线）",
    "total": 3.5,
    "min_dimension": 2,
    "needs_human_review": [],
    "summary": "洞察真实、钩子有效、执行可行，但创意偏常见模板，品牌融入偏弱；“全国销量第一，医院指定专用”触及极限用语和医疗背书红线……",
    "top_fixes": ["删除“全国销量第一”“医院指定专用”，改为可举证的表述……", "……"],
    "highlights": ["……"],
    "redlines": [
      { "id": "R1", "text": "违法违规或涉及敏感题材", "status": "未命中", "hits": "0/3", "evidence": "" },
      { "id": "R2", "text": "虚假或夸大承诺（含《广告法》极限用语、功效断言）", "status": "命中", "hits": "3/3",
        "evidence": "提案第 3 段“全国销量第一，医院指定专用”为广告法第九条禁止的极限用语……" }
    ],
    "dimensions": [
      { "id": "C1", "name": "策略契合", "weight": 0.2, "score": 4, "scores": [4, 4, 4], "spread": 0,
        "evidence": "目标人群与 brief 一致……", "issues": ["……"], "suggestions": ["……"] }
    ],
    "tech": null,
    "usage": { "prompt_tokens": 7260, "completion_tokens": 18950 }
  },
  "links": {
    "self": "{{BASE_URL}}/api/v1/reviews/20261021-6f38ae71",
    "report": "{{BASE_URL}}/api/v1/reviews/20261021-6f38ae71/report",
    "web": "{{BASE_URL}}/jobs/20261021-6f38ae71"
  }
}
```

| 字段 | 说明 |
|---|---|
| `status` | `queued` 排队中 → `running` 评审中 → `done` 完成 / `error` 失败 |
| `queue_position` | 排队位置，1 表示下一个开始 |
| `error` | 失败原因。余额不足或 Key 失效时为“API 鉴权或余额问题…”；服务重启时为“服务重启，任务中断” |
| `inputs.*.url` | 已上传文件的下载地址（需同样鉴权） |
| `result` | 仅在 `done` 时有值 |

### 评审结果（Result）

| 字段 | 说明 |
|---|---|
| `verdict` | 结论：`通过` / `修改后通过` / `驳回` / `驳回（命中红线）`，规则见下表 |
| `total` | 加权总分，1–5 |
| `min_dimension` | 最低的维度分 |
| `needs_human_review` | 需要人工复核的维度或红线 ID（多次采样分差 ≥ 2，或红线只在少数采样中命中） |
| `summary` | 100 字以内的总体评价 |
| `top_fixes` | 按优先级排序的修改建议 |
| `highlights` | 做得好的地方 |
| `redlines[]` | 红线检查结果，覆盖该关卡的所有红线 |
| `dimensions[]` | 各维度评分 |
| `tech` | 仅成片有值：程序测量的技术参数 |
| `usage` | 本次评审消耗的 token |
| `raw_runs` | 仅在 `include=raw_runs` 时返回：每次采样的模型原始 JSON |

**结论规则**（服务端计算）：

| 结论 | 条件 |
|---|---|
| 驳回（命中红线） | 任意红线状态为“命中” |
| 通过 | 总分 ≥ 4.0，且所有维度 ≥ 3 |
| 修改后通过 | 总分 ≥ 3.0，且所有维度 ≥ 2 |
| 驳回 | 其余情况 |

**红线 `status`**：

| 值 | 含义 | 是否影响结论 |
|---|---|---|
| `命中` | 多数采样判定命中 | 是，直接驳回 |
| `疑似（需人审）` | 少数采样判定命中 | 否，但会列入 `needs_human_review` |
| `未命中` | 所有采样都未命中 | 否 |

`hits` 为命中次数与采样次数之比，如 `2/3`。

**维度字段**：

| 字段 | 说明 |
|---|---|
| `score` | 多次采样的均值 |
| `scores` | 每次采样的得分 |
| `spread` | 极差，即最高分减最低分 |
| `evidence` | 打分依据，引用具体镜头、时间码或原文 |
| `issues` | 发现的问题 |
| `suggestions` | 可执行的修改建议 |

**成片技术参数 `tech`**：

| 键 | 示例 | 说明 |
|---|---|---|
| `时长(秒)` | 15.0 | |
| `视频编码` / `分辨率` / `画幅` / `帧率` | h264 / 1080x1920 / 0.562 (竖屏) / 25.0 | |
| `音频编码` / `采样率` / `声道` | aac / 48000 / mono | 无音轨时为 `无音轨` |
| `综合响度(LUFS)` | -15.0 | EBU R128 积分响度；抖音等平台参考 -14～-16 |
| `响度范围(LU)` | 4.5 | |
| `真峰值(dBTP)` | -1.2 | 应 ≤ -1 |
| `黑帧区间` | `["6s–7.52s"]` | 程序检测，非空即为技术硬伤 |
| `冻结帧起点` | `["6s"]` | 程序检测 |

## 评分标准

```http
GET /api/v1/rubrics
GET /api/v1/rubrics/{stage}
```

返回评审器实际使用的评分标准：维度、权重、评分要点、5 分和 2 分锚点、红线，以及结论规则。修改服务器上的 `rubrics.json` 后立即生效，不需要重启。

```json
{
  "stage": "video",
  "name": "G4 成片评审",
  "verdict_rules": { "pass": { "min_score": 4, "min_dimension": 3 }, "revise": { "min_score": 3, "min_dimension": 2 } },
  "dimensions": [
    { "id": "V1", "name": "开场吸引力", "weight": 0.15,
      "criteria": "前 3 秒能否留住观众：首帧冲击力、信息量、是否从动作中段切入",
      "anchor_5": "首帧即强视觉或强冲突，让人想继续看", "anchor_2": "开场平淡、慢热或以 Logo/空镜开场" }
  ],
  "redlines": [
    { "id": "R1", "text": "含《广告法》禁用的极限用语、虚假宣传或功效断言" },
    { "id": "R2", "text": "AI 生成合成内容缺少显式标识（《人工智能生成合成内容标识办法》2025-09-01 施行）" }
  ]
}
```

各关卡的维度：

| 关卡 | 维度（权重） | 红线数 |
|---|---|---|
| creative | C1 策略契合 20%、C2 用户洞察 15%、C3 创意新颖度 15%、C4 开场钩子 15%、C5 品牌融入 10%、C6 信息聚焦与情感连接 10%、C7 行动指引 5%、C8 可执行性 10% | 5 |
| storyboard | S1 叙事结构与节奏 20%、S2 镜头语言 15%、S3 连贯性 15%、S4 视听设计 10%、S5 创意还原度 15%、S6 平台与格式适配 10%、S7 可执行性/可生成性 15% | 4 |
| asset | A1 技术规格 15%、A2 视觉质量 20%、A3 一致性 20%、A4 品牌规范 15%、A5 分镜匹配度 15%、A6 版权与授权 15% | 3 |
| video | V1 开场吸引力 15%、V2 叙事与剪辑节奏 15%、V3 画面质量 15%、V4 声音质量 10%、V5 品牌与信息传达 15%、V6 前序还原度 10%、V7 行动指引 10%、V8 平台适配与包装 10% | 5 |

## 基准测试

基准测试衡量评审器本身是否靠谱。数据集共 420 个用例，标准答案来自构造：

- **基准样本**：合格样本，不应命中任何红线。
- **变体**：在基准样本上只注入一个已知缺陷。

根据评审器能否命中注入的红线、对应维度是否降分、只改格式时分数是否稳定，计算各项指标。用例划分为两部分：

- **开发集** S01–S02：用来调整评分标准。
- **测试集** S03–S08：只用来出报告，不根据它修改评分标准。

### 评测轮次列表

```http
GET /api/v1/benchmark/runs
```

```json
{
  "items": [
    { "name": "test_v1", "split": "test", "status": "done",
      "progress": { "done": 315, "total": 315 }, "cases": 315, "passed": 299, "pass_rate": 0.9492 },
    { "name": "dev_v3", "split": "dev", "status": "done",
      "progress": { "done": 105, "total": null }, "cases": 105, "passed": 98, "pass_rate": 0.9333 }
  ]
}
```

`status` 的取值：

| 值 | 含义 |
|---|---|
| `running` | 运行中 |
| `done` | 已完成 |
| `error` | 运行出错，见 `error` 字段 |
| `interrupted` | 服务器重启导致进程中断。用同名重新发起即可续跑，已完成的用例会跳过 |

### 轮次详情与指标

```http
GET /api/v1/benchmark/runs/{run}
GET /api/v1/benchmark/runs/{run}?include=rows     附带逐用例判定
```

```json
{
  "name": "test_v1", "split": "test", "status": "done",
  "progress": { "done": 315, "total": 315 },
  "spec": { "split": "test", "stages": [], "runs": 1, "workers": 4, "effort": "high", "total": 315 },
  "summary": {
    "model": "deepseek-flash", "runs": 1, "cases": 315, "passed": 299, "pass_rate": 0.9492,
    "usage": { "prompt_tokens": 1677002, "completion_tokens": 1972176 }, "avg_seconds": 46,
    "stages": ["creative", "storyboard", "asset", "video"],
    "metrics": [
      { "name": "红线召回（命中指定红线）", "values": { "creative": "100% (18/18)", "storyboard": "100% (30/30)", "asset": "96% (23/24)", "video": "100% (21/21)" } },
      { "name": "误报率（全部无红线用例）", "values": { "creative": "2% (1/66)", "storyboard": "3% (2/66)", "asset": "0% (0/36)", "video": "0% (0/54)" } }
    ],
    "variants": [{ "stage": "video", "variant": "v_black", "description": "中段插入 1.5 秒黑场", "passed": 6, "total": 6 }],
    "failures": [{ "case_id": "S05_asset_as_wrong_name", "reason": "应命中 ['R2']，实际命中 无，疑似 无" }]
  }
}
```

`metrics` 中的主要指标与目标：

| 指标 | 含义 | 目标 |
|---|---|---|
| 红线召回（命中指定红线） | 注入红线的用例中，命中该红线的比例 | ≥ 90% |
| 误报率（全部无红线用例） | 未注入红线的用例中，命中任一红线的比例 | ≤ 10% |
| 缺陷灵敏度（目标维度降 ≥1 分） | 注入质量缺陷后，目标维度比基准降 ≥ 1 分的比例 | ≥ 80% |
| 不变性（\|Δ总分\| ≤ 0.3） | 只改格式或加空话时，总分基本不变的比例 | ≥ 90% |
| 非目标维度平均 \|Δ\| | 注入一个缺陷时其他维度的连带变化 | 越小越好 |

`include=rows` 返回逐用例记录：

```json
{ "case_id": "S03_video_v_black", "stage": "video", "variant": "v_black", "kind": "redline",
  "total": 3.35, "verdict": "驳回（命中红线）", "hits": "R5", "expected_redlines": "R5",
  "target": "", "delta_target": "", "delta_total": -0.5, "pass": true }
```

### 发起评测轮次

```http
POST /api/v1/benchmark/runs
Content-Type: application/json
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 必填。轮次名，只能包含字母、数字、`_`、`-`，最长 40。建议用 `dev_v4`、`test_v2` 这类名字 |
| `split` | string | `dev` 或 `test`；不填则跑全部 420 例 |
| `stages` | string[] | 只跑指定关卡 |
| `scenarios` | string[] | 只跑指定行业样本，如 `["S03","S04"]` |
| `variants` | string[] | 只跑指定变体，如 `["base","inv_fluff"]` |
| `runs` | integer | 每例采样次数，1–3，默认 1。测稳定性时用 3 |
| `workers` | integer | 并发数，1–10，默认 4（服务器内存 1G，不建议超过 6） |
| `effort` | string | `low` / `high` / `max`，默认 `high` |
| `dry_run` | boolean | 为 `true` 时只返回用例数和费用预估，不运行 |

**建议先 dry_run**，确认用例数和预估费用：

```bash
curl -X POST {{BASE_URL}}/api/v1/benchmark/runs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"stab_v1","split":"test","variants":["base","inv_fluff"],"runs":3,"dry_run":true}'
```

```json
{
  "dry_run": true, "name": "stab_v1",
  "spec": { "split": "test", "stages": [], "scenarios": [], "variants": ["base", "inv_fluff"], "runs": 3, "workers": 4, "effort": "high" },
  "estimate": { "cases": 48, "cached": 0, "to_run": 48, "samples": 144, "estimated_cost_cny": 5.04 }
}
```

去掉 `dry_run` 后再次请求即正式启动，返回 202，然后轮询 `GET /benchmark/runs/{name}` 查看 `progress`。补充说明：

- 同名轮次中已完成的用例会直接复用。所以中断后重新发起同名轮次，就是断点续跑。
- 如果全部用例都已完成，重新发起只会重算一遍指标，不产生费用。
- 已有轮次在运行时，返回 409 `run_in_progress`。

费用按实测估算：每次采样约 ¥0.035。测试集 315 例、每例采样 1 次，约 ¥10.8。

## 用例库

### 用例列表

```http
GET /api/v1/cases?stage=asset&result=fail&limit=50
```

| 参数 | 说明 |
|---|---|
| `stage` | `creative` / `storyboard` / `asset` / `video` |
| `scenario` | 行业样本：S01 饮料、S02 美妆、S03 在线教育、S04 汽车、S05 手游、S06 金融理财、S07 母婴、S08 消费电子 |
| `kind` | `base` 基准 / `redline` 红线 / `quality` 质量缺陷 / `invariance` 不变性 |
| `variant` | 变体名，如 `v_black`、`sb_extreme`、`as_wrong_name` |
| `split` | `dev` / `test` |
| `result` | `pass` 评审器答对 / `fail` 答错 / `none` 未评测 |
| `run` | 只看某一轮次的结果；默认合并所有轮次（测试集用例取测试轮次） |
| `q` | 按用例号或缺陷描述搜索 |
| `limit` / `offset` | 分页，默认 50，最大 500 |

```json
{
  "total": 6, "limit": 50, "offset": 0,
  "items": [
    { "id": "S05_asset_as_wrong_name", "scenario": "S05", "industry": "手游", "split": "test",
      "stage": "asset", "kind": "redline", "variant": "as_wrong_name", "description": "主视觉产品名错误",
      "base_case_id": "S05_asset_base",
      "expect": { "redlines": ["R2"], "target": [], "no_redline": false, "verdict_not": ["通过"] },
      "evaluation": { "run": "test_v1", "passed": false, "verdict": "修改后通过", "total": 3.0,
                      "redlines_hit": [], "delta_target": null, "delta_total": -0.35 } }
  ]
}
```

`expect` 是标准答案，各字段含义：

| 字段 | 含义 |
|---|---|
| `redlines` | 应命中的红线 |
| `target` | 应比基准降 ≥ 1 分的维度 |
| `no_redline` | 不应命中任何红线 |

`evaluation` 是评审器的表现，各字段含义：

| 字段 | 含义 |
|---|---|
| `passed` | 是否答对 |
| `delta_target` | 目标维度相对基准的变化 |
| `delta_total` | 总分相对基准的变化 |

### 用例详情

```http
GET /api/v1/cases/{id}
GET /api/v1/cases/{id}?run=test_v1&include=raw_runs
GET /api/v1/cases/{id}?no_text              不返回文本材料内容（只返回下载地址）
```

在列表字段的基础上，增加以下内容：

- `inputs`：评审材料。每个文件包含 `name`、`kind`（`text` / `image` / `video`）和 `url`；文本文件还附带 `text` 内容。
- `result`：评审器的完整判断，结构同[评审结果](#评审结果-result)。

```json
{
  "id": "S03_video_v_black", "stage": "video", "kind": "redline", "description": "中段插入 1.5 秒黑场",
  "expect": { "redlines": ["R5"], "target": [], "no_redline": false, "verdict_not": ["通过"] },
  "evaluation": { "run": "test_v1", "passed": true, "verdict": "驳回（命中红线）", "total": 3.35, "redlines_hit": ["R5"] },
  "label_source": "构造（定向注入）",
  "inputs": {
    "files": [{ "name": "final.mp4", "kind": "video", "url": "{{BASE_URL}}/media/dataset/cases/S03_video_v_black/final.mp4" }],
    "context": [{ "name": "storyboard.md", "kind": "text", "url": "…", "text": "| 镜号 | 时长 | …" }],
    "transcript": { "name": "subtitles.srt", "kind": "text", "url": "…", "text": "1\n00:00:00,000 --> …" },
    "platform_hint": null
  },
  "result": { "verdict": "驳回（命中红线）", "total": 3.35, "tech": { "黑帧区间": ["6s–7.52s"], "冻结帧起点": ["6s"] }, "redlines": [], "dimensions": [] }
}
```

`/media/...` 下的文件地址支持 HTTP Range 请求，视频可以拖动进度。访问这些地址同样需要鉴权。

## 系统

### 健康检查

```http
GET /api/v1/health
```

```json
{
  "status": "ok", "version": "v1", "model": "deepseek-flash",
  "queue": { "running": 0, "queued": 0, "max_running": 2 },
  "deepseek_balance": { "available": true, "currency": "CNY", "total": 140.52 },
  "time": "2026-10-21T16:40:15.199Z"
}
```

建议监控系统每 5 分钟调用一次。`deepseek_balance.total` 低于 ¥20 时告警，余额耗尽后所有评审都会失败。

### OpenAPI 规范

```http
GET /api/v1/openapi.json
```

## 费用与性能

| 项目 | 实测 |
|---|---|
| 单次采样 token | 输入约 0.15 万（文本）到 1.5 万（成片，含关键帧图片），输出约 0.4–0.8 万 |
| 单次采样费用 | 约 ¥0.035 |
| 一次评审（默认 3 次采样） | 约 ¥0.1，耗时 40–90 秒（采样并发执行） |
| 基准测试测试集 315 例 × 1 次采样 | 约 ¥10.8，并发 10 时约 25 分钟 |

## 使用须知

- 评审器**听不到声音**，也**看不到连续运动**（只看关键帧）。配乐、口播、AI 视频闪烁和穿模，需要人工复核。
- 图片上的小字错字（如主视觉产品名写错一个字）识别不稳定。基准测试中，资产关卡的 `as_wrong_name` 变体在开发集 2 例中漏判 2 例，在测试集 6 例中漏判 1 例。
- `needs_human_review` 非空的结果，应交人工复核后再作决定。
- 红线检查用于在提交平台审核之前发现问题，不替代法务审核和平台审核。

## 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-21 | v1 | 首个版本：评审、评分标准、基准测试、用例库、健康检查、OpenAPI 规范、完成回调 |
