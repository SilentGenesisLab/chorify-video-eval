// OpenAPI 3.0 规范，可导入 Postman / Apifox / Swagger UI
const STAGE = { type: "string", enum: ["creative", "storyboard", "asset", "video"], description: "creative=G1 创意，storyboard=G2 分镜，asset=G3 资产，video=G4 成片" };
const ref = (n) => ({ $ref: `#/components/schemas/${n}` });
const ok = (schema, description = "成功") => ({ description, content: { "application/json": { schema } } });
const err = (description) => ({ description, content: { "application/json": { schema: ref("Error") } } });
const q = (name, schema, description, required = false) => ({ name, in: "query", required, schema, description });
const p = (name, description, schema = { type: "string" }) => ({ name, in: "path", required: true, schema, description });
const LIMIT = q("limit", { type: "integer", minimum: 1 }, "每页条数");
const OFFSET = q("offset", { type: "integer", minimum: 0, default: 0 }, "偏移量");

const reviewBody = {
  required: true,
  content: {
    "application/json": { schema: ref("ReviewRequest") },
    "multipart/form-data": {
      schema: {
        type: "object",
        properties: {
          files: { type: "array", items: { type: "string", format: "binary" }, description: "待评审文件，可多个" },
          context: { type: "array", items: { type: "string", format: "binary" }, description: "参考材料文件，可多个" },
          content: { type: "string", description: "待评审文本（与 files 至少提供一个）" },
          context_text: { type: "string", description: "参考材料文本" },
          transcript: { type: "string", description: "成片台词/字幕" },
          platform_hint: { type: "string" }, title: { type: "string" }, runs: { type: "integer", enum: [1, 2, 3] },
          effort: { type: "string", enum: ["low", "high", "max"] }, callback_url: { type: "string" },
          wait: { type: "integer", maximum: 300, description: "同步等待秒数" },
          stage: { ...STAGE, description: "仅在 POST /reviews 时需要" },
        },
      },
    },
  },
};

export function openapi(server) {
  return {
    openapi: "3.0.3",
    info: {
      title: "视频评审台 API",
      version: "1.0.0",
      description: "视频广告四关评审（创意、分镜、资产、成片）、评分标准、基准测试与用例库接口。评审由 deepseek-flash 完成，技术指标由程序测量。",
    },
    servers: [{ url: server }],
    security: [{ bearer: [] }, { apiKey: [] }],
    tags: [
      { name: "评审", description: "提交评审任务、查询结果" },
      { name: "评分标准", description: "四个关卡的维度、权重、红线与结论规则" },
      { name: "基准测试", description: "评审器在构造用例上的评测轮次与指标" },
      { name: "用例库", description: "420 个带标准答案的构造用例" },
      { name: "系统", description: "健康检查" },
    ],
    paths: {
      "/api/v1/reviews/{stage}": {
        post: {
          tags: ["评审"], summary: "提交评审", operationId: "createReview",
          description: "创建异步评审任务，立即返回 202 和任务号；传 wait（秒）可同步等待结果，完成则返回 200。",
          parameters: [{ ...p("stage", "评审关卡"), schema: STAGE }],
          requestBody: reviewBody,
          responses: { 200: ok(ref("Review"), "wait 期间已完成"), 202: ok(ref("Review"), "已排队"), 400: err("参数错误"), 401: err("未授权"), 413: err("文件超过 150MB"), 415: err("Content-Type 不支持") },
        },
      },
      "/api/v1/reviews": {
        get: {
          tags: ["评审"], summary: "评审任务列表", operationId: "listReviews",
          parameters: [q("stage", STAGE, "按关卡筛选"), q("status", { type: "string", enum: ["queued", "running", "done", "error"] }, "按状态筛选"), LIMIT, OFFSET],
          responses: { 200: ok({ type: "object", properties: { total: { type: "integer" }, limit: { type: "integer" }, offset: { type: "integer" }, items: { type: "array", items: ref("ReviewBrief") } } }) },
        },
        post: {
          tags: ["评审"], summary: "提交评审（关卡写在请求体）", operationId: "createReviewBody",
          description: "与 POST /api/v1/reviews/{stage} 相同，关卡通过请求体的 stage 字段指定。",
          requestBody: reviewBody,
          responses: { 200: ok(ref("Review")), 202: ok(ref("Review")), 400: err("参数错误") },
        },
      },
      "/api/v1/reviews/{id}": {
        get: {
          tags: ["评审"], summary: "查询评审任务", operationId: "getReview",
          parameters: [p("id", "任务号"), q("include", { type: "string", enum: ["raw_runs"] }, "附带每次采样的原始输出")],
          responses: { 200: ok(ref("Review")), 404: err("任务不存在") },
        },
        delete: {
          tags: ["评审"], summary: "删除评审任务", operationId: "deleteReview",
          description: "删除任务及其上传的文件。评审中的任务不能删除，排队中的任务会被取消。",
          parameters: [p("id", "任务号")],
          responses: { 204: { description: "已删除" }, 404: err("任务不存在"), 409: err("任务评审中") },
        },
      },
      "/api/v1/reviews/{id}/report": {
        get: {
          tags: ["评审"], summary: "下载 Markdown 评审报告", operationId: "getReviewReport",
          parameters: [p("id", "任务号")],
          responses: { 200: { description: "Markdown 报告", content: { "text/markdown": { schema: { type: "string" } } } }, 409: err("评审未完成") },
        },
      },
      "/api/v1/rubrics": {
        get: { tags: ["评分标准"], summary: "全部关卡的评分标准", operationId: "listRubrics", responses: { 200: ok({ type: "object" }) } },
      },
      "/api/v1/rubrics/{stage}": {
        get: {
          tags: ["评分标准"], summary: "单个关卡的评分标准", operationId: "getRubric",
          parameters: [{ ...p("stage", "关卡"), schema: STAGE }],
          responses: { 200: ok(ref("Rubric")), 404: err("关卡不存在") },
        },
      },
      "/api/v1/benchmark/runs": {
        get: { tags: ["基准测试"], summary: "评测轮次列表", operationId: "listRuns", responses: { 200: ok({ type: "object", properties: { items: { type: "array", items: ref("RunBrief") } } }) } },
        post: {
          tags: ["基准测试"], summary: "发起评测轮次", operationId: "startRun",
          description: "在服务器后台运行 run_benchmark.py。同名轮次已完成的用例会跳过（断点续跑）。同一时间只允许一个轮次运行。建议先用 dry_run 预估用例数和费用。",
          requestBody: { required: true, content: { "application/json": { schema: ref("RunRequest") } } },
          responses: { 200: ok(ref("RunStart"), "dry_run 预估"), 202: ok(ref("RunStart"), "已启动"), 400: err("参数错误"), 409: err("已有轮次在运行") },
        },
      },
      "/api/v1/benchmark/runs/{run}": {
        get: {
          tags: ["基准测试"], summary: "评测轮次详情与指标", operationId: "getRun",
          parameters: [p("run", "轮次名"), q("include", { type: "string", enum: ["rows"] }, "附带逐用例判定")],
          responses: { 200: ok(ref("Run")), 404: err("轮次不存在") },
        },
      },
      "/api/v1/cases": {
        get: {
          tags: ["用例库"], summary: "用例列表", operationId: "listCases",
          parameters: [
            q("stage", STAGE, "关卡"), q("scenario", { type: "string", example: "S03" }, "行业样本 S01–S08"),
            q("kind", { type: "string", enum: ["base", "redline", "quality", "invariance"] }, "用例类型"),
            q("variant", { type: "string", example: "v_black" }, "变体（注入的缺陷）"), q("split", { type: "string", enum: ["dev", "test"] }, "数据集划分"),
            q("result", { type: "string", enum: ["pass", "fail", "none"] }, "评审器是否答对；none=未评测"),
            q("run", { type: "string" }, "只看某个评测轮次的结果；默认合并所有轮次"), q("q", { type: "string" }, "按用例号或缺陷描述搜索"), LIMIT, OFFSET,
          ],
          responses: { 200: ok({ type: "object", properties: { total: { type: "integer" }, limit: { type: "integer" }, offset: { type: "integer" }, items: { type: "array", items: ref("CaseBrief") } } }) },
        },
      },
      "/api/v1/cases/{id}": {
        get: {
          tags: ["用例库"], summary: "用例详情", operationId: "getCase",
          description: "包含标准答案、输入材料（文本内容与图片/视频下载地址）和评审器的完整判断。",
          parameters: [p("id", "用例号，如 S03_video_v_black"), q("run", { type: "string" }, "评测轮次"), q("include", { type: "string", enum: ["raw_runs"] }, "附带原始输出"), q("no_text", { type: "boolean" }, "不返回文本材料内容")],
          responses: { 200: ok(ref("Case")), 404: err("用例不存在") },
        },
      },
      "/api/v1/health": {
        get: { tags: ["系统"], summary: "健康检查", operationId: "health", description: "服务状态、评审队列、DeepSeek 账户余额。", responses: { 200: ok({ type: "object" }) } },
      },
    },
    components: {
      securitySchemes: {
        bearer: { type: "http", scheme: "bearer", description: "Authorization: Bearer <API Token>" },
        apiKey: { type: "apiKey", in: "header", name: "X-API-Key" },
      },
      schemas: {
        Error: { type: "object", properties: { error: { type: "object", properties: { code: { type: "string" }, message: { type: "string" } } } } },
        FileRef: {
          type: "object", description: "三选一：content_base64（二进制）、text（文本）、url（服务器下载）",
          properties: { name: { type: "string", description: "文件名，需带扩展名，决定按文本/图片/视频处理" }, content_base64: { type: "string" }, text: { type: "string" }, url: { type: "string" } },
        },
        ReviewRequest: {
          type: "object",
          properties: {
            stage: { ...STAGE, description: "仅在 POST /reviews 时需要" },
            content: { oneOf: [{ type: "string" }, { type: "array", items: { type: "string" } }], description: "待评审文本，如创意提案、分镜表" },
            files: { type: "array", items: ref("FileRef"), description: "待评审文件：图片、视频、文本" },
            context: { oneOf: [{ type: "string" }, { type: "array", items: { type: "string" } }], description: "参考材料文本：brief、上一关材料、品牌规范" },
            context_files: { type: "array", items: ref("FileRef") },
            transcript: { type: "string", description: "成片台词/字幕（模型听不到声音）" },
            platform_hint: { type: "string", description: "投放平台与规格，默认抖音/视频号竖屏 9:16" },
            runs: { type: "integer", enum: [1, 2, 3], default: 3, description: "采样次数（panel 模式下是每位评审员的采样次数）" },
            mode: { type: "string", enum: ["sample", "panel"], default: "sample", description: "sample：一位评审员按整套标准多次采样；panel：分维度评审团，各评审员只评自己负责的维度，合规评审员判红线，并发执行" },
            effort: { type: "string", enum: ["low", "high", "max"], default: "high" },
            title: { type: "string" },
            callback_url: { type: "string", description: "完成（或失败）后 POST Review 对象到该地址" },
            wait: { type: "integer", minimum: 0, maximum: 300, default: 0, description: "同步等待秒数" },
          },
        },
        Redline: { type: "object", properties: { id: { type: "string", example: "R2" }, text: { type: "string" }, status: { type: "string", enum: ["命中", "疑似（需人审）", "未命中"] }, hits: { type: "string", example: "3/3" }, evidence: { type: "string" } } },
        Dimension: {
          type: "object",
          properties: {
            id: { type: "string", example: "S1" }, name: { type: "string" }, weight: { type: "number" }, score: { type: "number", description: "多次采样均值" },
            scores: { type: "array", items: { type: "integer" } }, spread: { type: "integer", description: "极差" },
            evidence: { type: "string" }, issues: { type: "array", items: { type: "string" } }, suggestions: { type: "array", items: { type: "string" } },
          },
        },
        Result: {
          type: "object",
          properties: {
            verdict: { type: "string", enum: ["通过", "修改后通过", "驳回", "驳回（命中红线）"] }, total: { type: "number" }, min_dimension: { type: "number" },
            needs_human_review: { type: "array", items: { type: "string" } }, summary: { type: "string" },
            top_fixes: { type: "array", items: { type: "string" } }, highlights: { type: "array", items: { type: "string" } },
            redlines: { type: "array", items: ref("Redline") }, dimensions: { type: "array", items: ref("Dimension") },
            tech: { type: "object", nullable: true, description: "成片技术参数（程序测量）" },
            usage: { type: "object", properties: { prompt_tokens: { type: "integer" }, completion_tokens: { type: "integer" } } },
            model: { type: "string", description: "实际使用的评审模型" }, mode: { type: "string", enum: ["sample", "panel"] },
            panels: { type: "array", nullable: true, description: "panel 模式下的评审团编制", items: { type: "object", properties: { id: { type: "string" }, name: { type: "string" }, dimensions: { type: "array", items: { type: "string" } }, redlines: { type: "boolean" } } } },
            raw_runs: { type: "array", items: { type: "object" } },
          },
        },
        Review: {
          type: "object",
          properties: {
            id: { type: "string" }, stage: STAGE, title: { type: "string" }, status: { type: "string", enum: ["queued", "running", "done", "error"] },
            error: { type: "string", nullable: true }, queue_position: { type: "integer", nullable: true },
            created_at: { type: "string", format: "date-time" }, started_at: { type: "string", format: "date-time", nullable: true },
            finished_at: { type: "string", format: "date-time", nullable: true }, elapsed_seconds: { type: "integer", nullable: true },
            params: { type: "object" }, inputs: { type: "object" }, result: { ...ref("Result"), nullable: true },
            links: { type: "object", properties: { self: { type: "string" }, report: { type: "string" }, web: { type: "string" } } },
          },
        },
        ReviewBrief: { type: "object", description: "Review 去掉 inputs 和 result，增加 verdict、total" },
        Rubric: { type: "object", properties: { stage: STAGE, name: { type: "string" }, verdict_rules: { type: "object" }, dimensions: { type: "array", items: { type: "object" } }, redlines: { type: "array", items: { type: "object" } } } },
        RunRequest: {
          type: "object", required: ["name"],
          properties: {
            name: { type: "string", example: "test_v2" }, split: { type: "string", enum: ["dev", "test"] },
            stages: { type: "array", items: STAGE }, scenarios: { type: "array", items: { type: "string" } }, variants: { type: "array", items: { type: "string" } },
            runs: { type: "integer", enum: [1, 2, 3], default: 1 }, workers: { type: "integer", minimum: 1, maximum: 10, default: 4 },
            effort: { type: "string", enum: ["low", "high", "max"], default: "high" }, dry_run: { type: "boolean", default: false },
          },
        },
        RunStart: { type: "object", properties: { dry_run: { type: "boolean" }, name: { type: "string" }, spec: { type: "object" }, estimate: { type: "object", properties: { cases: { type: "integer" }, cached: { type: "integer" }, to_run: { type: "integer" }, samples: { type: "integer" }, estimated_cost_cny: { type: "number" } } } } },
        RunBrief: { type: "object", properties: { name: { type: "string" }, split: { type: "string" }, status: { type: "string", enum: ["running", "done", "error", "interrupted", "unknown"] }, progress: { type: "object" }, cases: { type: "integer" }, passed: { type: "integer" }, pass_rate: { type: "number" } } },
        Run: { type: "object", description: "RunBrief + spec + summary（metrics、variants、failures；include=rows 时含 rows）" },
        CaseBrief: {
          type: "object",
          properties: {
            id: { type: "string" }, scenario: { type: "string" }, industry: { type: "string" }, split: { type: "string" }, stage: STAGE,
            kind: { type: "string" }, variant: { type: "string" }, description: { type: "string" }, base_case_id: { type: "string", nullable: true },
            expect: { type: "object", properties: { redlines: { type: "array", items: { type: "string" } }, target: { type: "array", items: { type: "string" } }, no_redline: { type: "boolean" } } },
            evaluation: { type: "object", nullable: true, properties: { run: { type: "string" }, passed: { type: "boolean" }, verdict: { type: "string" }, total: { type: "number" }, redlines_hit: { type: "array", items: { type: "string" } }, delta_target: { type: "number", nullable: true }, delta_total: { type: "number", nullable: true } } },
          },
        },
        Case: { type: "object", description: "CaseBrief + label_source + inputs（文件名、类型、下载地址、文本内容）+ result（Result）" },
      },
    },
  };
}
