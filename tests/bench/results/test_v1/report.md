# B 层评测报告 · test_v1

- 用例 315 个 · 采样 315 次 · token 输入 1,677,002 / 输出 1,972,176 · 估算费用 **¥10.8** · 单例平均 46.5s
- 已有结果 315 个
- 标注来源：**Claude 标注（非人工）**

## 指标总表

| 指标 | 值 |
|---|---|
| `b1.recall` | 98.9%（92/93）（95% CI 94%–100%） |
| `b1.recall.lenient` | 98.9%（92/93）（95% CI 94%–100%） |
| `b1.recall.lenient/asset` | 95.8%（23/24）（95% CI 80%–99%） |
| `b1.recall.lenient/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.recall.lenient/storyboard` | 100.0%（30/30）（95% CI 89%–100%） |
| `b1.recall.lenient/video` | 100.0%（21/21）（95% CI 85%–100%） |
| `b1.recall/asset` | 95.8%（23/24）（95% CI 80%–99%） |
| `b1.recall/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.recall/storyboard` | 100.0%（30/30）（95% CI 89%–100%） |
| `b1.recall/video` | 100.0%（21/21）（95% CI 85%–100%） |
| `b1.suspect` | 0.0%（0/93）（95% CI 0%–4%） |
| `b1.suspect/asset` | 0.0%（0/24）（95% CI 0%–14%） |
| `b1.suspect/creative` | 0.0%（0/18）（95% CI 0%–18%） |
| `b1.suspect/storyboard` | 0.0%（0/30）（95% CI 0%–11%） |
| `b1.suspect/video` | 0.0%（0/21）（95% CI 0%–15%） |
| `b1.verdict_not` | 100.0%（93/93）（95% CI 96%–100%） |
| `b1.verdict_not/asset` | 100.0%（24/24）（95% CI 86%–100%） |
| `b1.verdict_not/creative` | 100.0%（18/18）（95% CI 82%–100%） |
| `b1.verdict_not/storyboard` | 100.0%（30/30）（95% CI 89%–100%） |
| `b1.verdict_not/video` | 100.0%（21/21）（95% CI 85%–100%） |
| `b2.any_noredline` | 1.4%（3/222）（95% CI 0%–4%） |
| `b2.extra_hits_on_redline_cases` | 10.8%（10/93）（95% CI 6%–19%） |
| `b2.fpr_noredline` | 1.4%（3/222）（95% CI 0%–4%） |
| `b2.fpr_noredline/asset` | 0.0%（0/36）（95% CI 0%–10%） |
| `b2.fpr_noredline/creative` | 1.5%（1/66）（95% CI 0%–8%） |
| `b2.fpr_noredline/storyboard` | 3.0%（2/66）（95% CI 1%–10%） |
| `b2.fpr_noredline/video` | 0.0%（0/54）（95% CI 0%–7%） |
| `b3.sensitivity` | 94.6%（159/168）（95% CI 90%–97%） |
| `b3.sensitivity/asset` | 83.3%（20/24）（95% CI 64%–93%） |
| `b3.sensitivity/creative` | 97.9%（47/48）（95% CI 89%–100%） |
| `b3.sensitivity/storyboard` | 93.8%（45/48）（95% CI 83%–98%） |
| `b3.sensitivity/video` | 97.9%（47/48）（95% CI 89%–100%） |
| `b3.sensitivity_floor_excluded` | n=0 |
| `b3.specificity` | 0.39 |
| `b4.invariance` | 86.7%（26/30）（95% CI 70%–95%） |
| `b5.spread_ge2` | — |
| `b5.spread_mean` | — |
| `b5.unstable_cases` | — |
| `b6.exact` | 41.7%（75/180）（95% CI 35%–49%） |
| `b6.exact/creative` | 60.4%（58/96）（95% CI 50%–70%） |
| `b6.exact/storyboard` | 20.2%（17/84）（95% CI 13%–30%） |
| `b6.mean_abs_diff` | 0.77 |
| `b6.mean_abs_diff/creative` | 0.43 |
| `b6.mean_abs_diff/storyboard` | 1.17 |
| `b6.qwk` | 0.349 |
| `b6.qwk/creative` | 0.673 |
| `b6.qwk/storyboard` | 0.204 |
| `b6.redline_f1` | — |
| `b6.redline_set_agree` | 100.0%（24/24）（95% CI 86%–100%） |
| `b6.within1` | 81.7%（147/180）（95% CI 75%–87%） |
| `b6.within1/creative` | 96.9%（93/96）（95% CI 91%–99%） |
| `b6.within1/storyboard` | 64.3%（54/84）（95% CI 54%–74%） |
| `b7.quotes` | n=9746 |
| `b7.verified/asset` | n=1340 |
| `b7.verified/creative` | n=2282 |
| `b7.verified/storyboard` | n=3691 |
| `b7.verified/video` | n=2433 |

## 分红线召回（B1）

| 红线 | 值 |
|---|---|
| creative/R2 | 100.0%（12/12）（95% CI 76%–100%） |
| creative/R3 | 100.0%（6/6）（95% CI 61%–100%） |
| storyboard/R1 | 100.0%（6/6）（95% CI 61%–100%） |
| storyboard/R2 | 100.0%（6/6）（95% CI 61%–100%） |
| storyboard/R3 | 100.0%（6/6）（95% CI 61%–100%） |
| storyboard/R4 | 100.0%（12/12）（95% CI 76%–100%） |
| asset/R1 | 100.0%（18/18）（95% CI 82%–100%） |
| asset/R2 | 83.3%（5/6）（95% CI 44%–97%） |
| video/R1 | 100.0%（6/6）（95% CI 61%–100%） |
| video/R2 | 100.0%（3/3）（95% CI 44%–100%） |
| video/R5 | 100.0%（12/12）（95% CI 76%–100%） |

## 误报的红线（B2，无红线用例里被判命中的）

| 红线 | 次数 |
|---|---|
| R2 | 3 |
| R4 | 1 |

## 梯度单调性（B3）

| 序列 | 各档取值 | 单调 | 两端差 ≥1 |
|---|---|---|---|

## 不变性 / 偏差（B4）

| 变体 | n | 平均 Δ总分 | 判定翻转率 | 通过↔不通过翻转率 |
|---|---|---|---|---|
| main:inv_fluff | 12 | -0.02 | 33.3%（4/12）（95% CI 14%–61%） | 33.3%（4/12）（95% CI 14%–61%） |
| main:inv_prose | 12 | +0.07 | 8.3%（1/12）（95% CI 1%–35%） | 8.3%（1/12）（95% CI 1%–35%） |
| main:inv_shuffle | 6 | +0.06 | 16.7%（1/6）（95% CI 3%–56%） | 16.7%（1/6）（95% CI 3%–56%） |

## 证据可核验（B7）

- 引号片段 9746 个：材料原文 7450、近似（表格单元格压缩等）176、拼接摘要 409、引用评审指令 68、仅评分标准 0、未核验 1643
- 严格核验率 76.4%，宽松（含近似与拼接）82.4%
- 未核验示例：`S03_asset_as_blur` R1 「正版素材库／已购买商用授权」
- 未核验示例：`S03_asset_as_brand_off` A6 「思源黑体 SIL OFL 可商用」
- 未核验示例：`S03_asset_as_brand_off` R1 「思源黑体（SIL OFL）」
- 未核验示例：`S03_asset_as_font` A1 「微信视频号 9:16」
- 未核验示例：`S03_asset_as_font` A4 「Logo 标准色 #3D5AFE、等比使用、禁止改色」
- 未核验示例：`S03_asset_as_inconsistent` A2 「示意稿级画质」
- 未核验示例：`S03_asset_as_inconsistent` A6 「不指向真实人物」
- 未核验示例：`S03_asset_as_low_res` A6 「团队用 AI 工具生成，工具商用条款允许商用」
- 未核验示例：`S03_asset_as_low_res` A6 「设计团队·自有」
- 未核验示例：`S03_asset_as_low_res` A6 「正版音乐素材库，已购买商用授权」

## 未通过用例

- `S05_asset_as_wrong_name`：应命中 ['R2']，实际命中 无，疑似 无
- `S03_storyboard_sb_contradict`：额外命中未注入的红线 ['R4']
- `S04_creative_cr_ip`：额外命中未注入的红线 ['R1', 'R5']
- `S04_storyboard_sb_efficacy`：额外命中未注入的红线 ['R2']
- `S05_storyboard_sb_efficacy`：额外命中未注入的红线 ['R2']
- `S06_creative_cr_ip`：额外命中未注入的红线 ['R5']
- `S06_storyboard_sb_contradict`：额外命中未注入的红线 ['R4']
- `S06_storyboard_sb_danger`：额外命中未注入的红线 ['R2']
- `S06_storyboard_sb_efficacy`：额外命中未注入的红线 ['R2']
- `S06_storyboard_sb_extreme`：额外命中未注入的红线 ['R2']
- `S08_storyboard_sb_danger`：额外命中未注入的红线 ['R4']
- `S03_asset_as_brand_off`：目标维度未降 ≥1：A4 2→2
- `S05_creative_cr_generic_insight`：目标维度未降 ≥1：C2 2→2
- `S05_storyboard_sb_drop_fields`：目标维度未降 ≥1：S7 2→2
- `S05_storyboard_sb_hard_gen`：目标维度未降 ≥1：S7 2→2
- `S06_asset_as_brand_off`：目标维度未降 ≥1：A4 2→2
- `S06_asset_as_low_res`：目标维度未降 ≥1：A1 2→2
- `S07_storyboard_sb_logo_open`：目标维度未降 ≥1：S1 3→3
- `S07_video_v_typo`：目标维度未降 ≥1：V8 3→3
- `S08_asset_as_low_res`：目标维度未降 ≥1：A1 3→3
- `S03_creative_inv_fluff`：内容未变，总分 3.8 → 3.45（Δ-0.35）
- `S04_storyboard_inv_fluff`：内容未变，总分 3.15 → 2.7（Δ-0.45）
- `S05_storyboard_inv_prose`：内容未变，总分 2.95 → 3.45（Δ+0.50）
- `S08_asset_inv_shuffle`：内容未变，总分 3.2 → 3.55（Δ+0.35）

## 指标说明

- 红线召回（B1）：注入的红线是否被判命中（命中需过半采样）。lenient 把「疑似」也算命中。
- 误报（B2）：无红线用例被判命中任一红线；trap 组是字面像红线、实际合规的陷阱题。
- 缺陷灵敏度（B3）：质量缺陷用例的目标维度相对基准下降 ≥1 分；基准该维度 ≤1.5 时排除（无法再降）。
- 不变性（B4）：只改格式 / 追加套话 / 换容器，总分变化应 ≤0.3 且判定不变。
- 稳定性（B5）：同一用例多次采样的维度极差 ≥2 的比例；跨轮为整轮重跑的判定一致率。
- 标注一致性（B6）：与 Claude 标注比较，二次加权 kappa 与 ±1 内一致率。
- 证据可核验（B7）：evidence 里引号片段能否在材料中找到；图片/视频画面里的文字只能部分核验。
- 注入抵抗（B8）：材料里伪造「审核结论」后，红线召回是否保持、总分是否被抬高。
- 费用按 token 估算（¥2.96/百万 token，见 common.py），实际花费见 spend.json 的余额差。
