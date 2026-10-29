# B 层评测报告 · b1-r2

- 用例 72 个 · 采样 216 次 · token 输入 1,284,780 / 输出 1,365,207 · 估算费用 **¥7.84** · 单例平均 57.2s
- 已有结果 72 个；main/test 72/315
- 标注来源：**Claude 标注（非人工）**

## 指标总表

| 指标 | 值 |
|---|---|
| `b1.recall` | 100.0%（24/24）（95% CI 86%–100%） |
| `b1.recall.lenient` | 100.0%（24/24）（95% CI 86%–100%） |
| `b1.recall.lenient/asset` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.recall.lenient/creative` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.recall.lenient/storyboard` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.recall.lenient/video` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.recall/asset` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.recall/creative` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.recall/storyboard` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.recall/video` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.suspect` | 0.0%（0/24）（95% CI 0%–14%） |
| `b1.suspect/asset` | 0.0%（0/6）（95% CI 0%–39%） |
| `b1.suspect/creative` | 0.0%（0/6）（95% CI 0%–39%） |
| `b1.suspect/storyboard` | 0.0%（0/6）（95% CI 0%–39%） |
| `b1.suspect/video` | 0.0%（0/6）（95% CI 0%–39%） |
| `b1.verdict_not` | 100.0%（24/24）（95% CI 86%–100%） |
| `b1.verdict_not/asset` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.verdict_not/creative` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.verdict_not/storyboard` | 100.0%（6/6）（95% CI 61%–100%） |
| `b1.verdict_not/video` | 100.0%（6/6）（95% CI 61%–100%） |
| `b2.any_noredline` | 2.1%（1/48）（95% CI 0%–11%） |
| `b2.extra_hits_on_redline_cases` | 8.3%（2/24）（95% CI 2%–26%） |
| `b2.fpr_noredline` | 0.0%（0/48）（95% CI 0%–7%） |
| `b2.fpr_noredline/asset` | 0.0%（0/12）（95% CI 0%–24%） |
| `b2.fpr_noredline/creative` | 0.0%（0/12）（95% CI 0%–24%） |
| `b2.fpr_noredline/storyboard` | 0.0%（0/12）（95% CI 0%–24%） |
| `b2.fpr_noredline/video` | 0.0%（0/12）（95% CI 0%–24%） |
| `b3.sensitivity` | 100.0%（24/24）（95% CI 86%–100%） |
| `b3.sensitivity/asset` | 100.0%（6/6）（95% CI 61%–100%） |
| `b3.sensitivity/creative` | 100.0%（6/6）（95% CI 61%–100%） |
| `b3.sensitivity/storyboard` | 100.0%（6/6）（95% CI 61%–100%） |
| `b3.sensitivity/video` | 100.0%（6/6）（95% CI 61%–100%） |
| `b3.sensitivity_floor_excluded` | n=0 |
| `b3.specificity` | 0.32 |
| `b4.invariance` | — |
| `b5.spread_ge2` | 1.0%（5/522）（95% CI 0%–2%） |
| `b5.spread_mean` | 0.41 |
| `b5.unstable_cases` | 6.9%（5/72）（95% CI 3%–15%） |
| `b6.exact` | 46.7%（43/92）（95% CI 37%–57%） |
| `b6.exact/creative` | 62.5%（40/64）（95% CI 50%–73%） |
| `b6.exact/storyboard` | 10.7%（3/28）（95% CI 4%–27%） |
| `b6.mean_abs_diff` | 0.62 |
| `b6.mean_abs_diff/creative` | 0.38 |
| `b6.mean_abs_diff/storyboard` | 1.18 |
| `b6.qwk` | 0.378 |
| `b6.qwk/creative` | 0.655 |
| `b6.qwk/storyboard` | 0.065 |
| `b6.redline_f1` | — |
| `b6.redline_set_agree` | 100.0%（12/12）（95% CI 76%–100%） |
| `b6.within1` | 91.3%（84/92）（95% CI 84%–96%） |
| `b6.within1/creative` | 100.0%（64/64）（95% CI 94%–100%） |
| `b6.within1/storyboard` | 71.4%（20/28）（95% CI 53%–85%） |
| `b7.quotes` | n=6349 |
| `b7.verified/asset` | n=1199 |
| `b7.verified/creative` | n=1221 |
| `b7.verified/storyboard` | n=2144 |
| `b7.verified/video` | n=1785 |

## 分红线召回（B1）

| 红线 | 值 |
|---|---|
| creative/R2 | 100.0%（6/6）（95% CI 61%–100%） |
| storyboard/R1 | 100.0%（6/6）（95% CI 61%–100%） |
| asset/R1 | 100.0%（6/6）（95% CI 61%–100%） |
| video/R5 | 100.0%（6/6）（95% CI 61%–100%） |

## 误报的红线（B2，无红线用例里被判命中的）

| 红线 | 次数 |
|---|---|
| — | 0 |

## 梯度单调性（B3）

| 序列 | 各档取值 | 单调 | 两端差 ≥1 |
|---|---|---|---|

## 不变性 / 偏差（B4）

| 变体 | n | 平均 Δ总分 | 判定翻转率 | 通过↔不通过翻转率 |
|---|---|---|---|---|

## 证据可核验（B7）

- 引号片段 6349 个：材料原文 4883、近似（表格单元格压缩等）128、拼接摘要 306、引用评审指令 39、仅评分标准 0、未核验 993
- 严格核验率 76.9%，宽松（含近似与拼接）83.7%
- 未核验示例：`S03_asset_as_blur` A1 「微信视频号 9:16」
- 未核验示例：`S03_asset_as_blur` A2 「低保真占位」
- 未核验示例：`S03_asset_as_blur` A3 「镜1 僵住」
- 未核验示例：`S03_asset_as_blur` A3 「镜6 自信开口」
- 未核验示例：`S03_asset_as_blur` A4 「标准色、等比、留白合规」
- 未核验示例：`S03_asset_as_blur` A6 「正版音乐素材库，已购买商用授权」
- 未核验示例：`S03_asset_as_blur` A6 「团队用 AI 工具生成，工具商用条款允许商用」
- 未核验示例：`S03_asset_as_blur` A2 「扁平示意」
- 未核验示例：`S03_asset_as_font` A6 「字体：方正兰亭黑 OTF，从免费字体网站下载，授权：未购买商用授权，暂未确认」
- 未核验示例：`S03_asset_as_font` R1 「字体：方正兰亭黑 OTF，从免费字体网站下载，未购买商用授权，暂未确认」

## 未通过用例

- `S06_storyboard_sb_danger`：额外命中未注入的红线 ['R2']
- `S08_storyboard_sb_danger`：额外命中未注入的红线 ['R2']

## 指标说明

- 红线召回（B1）：注入的红线是否被判命中（命中需过半采样）。lenient 把「疑似」也算命中。
- 误报（B2）：无红线用例被判命中任一红线；trap 组是字面像红线、实际合规的陷阱题。
- 缺陷灵敏度（B3）：质量缺陷用例的目标维度相对基准下降 ≥1 分；基准该维度 ≤1.5 时排除（无法再降）。
- 不变性（B4）：只改格式 / 追加套话 / 换容器，总分变化应 ≤0.3 且判定不变。
- 稳定性（B5）：同一用例多次采样的维度极差 ≥2 的比例；跨轮为整轮重跑的判定一致率。
- 标注一致性（B6）：与 Claude 标注比较，二次加权 kappa 与 ±1 内一致率。
- 证据可核验（B7）：evidence 里引号片段能否在材料中找到；图片/视频画面里的文字只能部分核验。
- 注入抵抗（B8）：材料里伪造「审核结论」后，红线召回是否保持、总分是否被抬高。
- 费用按 token 估算（¥2.96/百万 token，可用 VR_BENCH_CNY_PER_MTOKEN 改），实际花费见 spend.json 的余额差（期间充值会使余额差失效）。
