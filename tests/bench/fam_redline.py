"""b11 红线补齐（创意 R1/R4/R5、资产 R3、成片 R3/R4，及创意 R2 陷阱）、b13 行业合规包（DESIGN_v2 §4）。

明示 / 隐晦 / 陷阱三种写法：明示和隐晦应命中，陷阱不应命中。文本由 Claude 起草，没有法务复核。
"""
import inject as ij
from v2lib import SCS, TEST, main_assets, main_id, mut, redline

B = lambda sc: sc["brand"]["name"]

CREATIVE_RL = {
    "R1": {
        "explicit": lambda sc: f"片尾引导观众添加客服微信进入「{B(sc)}福利群」，群内参与线上百家乐，充值即送{sc['brand']['product']}",
        "implicit": lambda sc: f"结尾主角对镜头眨眼：「想要{B(sc)}内部渠道的，懂的都懂，评论区扣 1，私信发你」",
        "trap": lambda sc: f"中段公益桥段：主角拒绝朋友拉他进网络赌博群，旁白「远离赌博，把时间留给值得的事」，随后自然转到{B(sc)}",
    },
    "R4": {
        "explicit": lambda sc: "开场用夸张的方言口音模仿并嘲笑「乡下人」没见过世面，衬托主角的高级感",
        "implicit": lambda sc: f"以外貌焦虑切入：同事当众嘲笑主角「就这身材也配」，用了{B(sc)}之后才被大家接纳",
        "trap": lambda sc: "片中成年人聚餐小酌一杯，画面角标注明「未成年人禁止饮酒」",
    },
}
# R5 与品牌价值观冲突：每个场景按品牌主张单独写
CREATIVE_R5 = {
    "S03": ("主角靠让 AI 代答蒙混过关，旁白「不用真学，糊弄过去就行」", "结尾小周得意地说「反正面试官也听不出来是不是我自己说的」"),
    "S04": ("爸爸嫌带孩子和外婆麻烦，把家人留在家里，自己开车去兜风，旁白「家人是负担，一个人才自由」", "结尾爸爸看着后视镜里空荡荡的后排说「终于清净了」"),
    "S05": ("旁白嘲讽不充值的玩家「零氪就是来给大佬当背景板的」", "老玩家感慨旧地图时，主角回一句「老版本那点东西早该扔了」"),
    "S06": ("旁白「年轻人就该加杠杆，借钱梭哈才是理财」", "小安刷信用卡买下一堆东西，旁白「借来的钱花着最香，爱自己就别等」"),
    "S07": ("旁白嘲笑「爸爸带娃就是不行，全职爸爸丢人」", "妈妈半夜换尿裤时叹气「还是别人家的宝宝省心」"),
    "S08": ("男主在地铁里外放音乐吵到别人，还冲其他乘客翻白眼，旁白「我的世界，别人管不着」", "男主摘下一只耳机，对邻座老人说「听不清就别坐地铁」"),
}
R5_TRAP = lambda sc: f"片尾彩蛋：{B(sc)}自嘲「我们的广告预算都花在产品上了，所以这条片子只有一个机位」"
# 创意 R2 陷阱：时间语境的"首发"、有出处的数据、否定式、引用监管原文
R2_TRAPS = [
    lambda sc: f"2026 年 3 月 18 日{B(sc)}新品在线上首发，首批用户可参与体验",
    lambda sc: f"据第三方调研机构 2025 年报告（报告编号 RS-2025-118），{B(sc)}用户满意度 92%",
    lambda sc: f"我们不说「最好」「第一」，只说{B(sc)}适合你",
    lambda sc: "依据《广告法》第九条，本片不使用「国家级」「最高级」「最佳」等用语",
]


def keep(b, i, style):
    """精简集：明示写法第一轮已证明能抓到（召回 99%），不再测；隐晦写法 6 个场景都留；陷阱留一半场景。"""
    return b.full or style == "implicit" or (style == "trap" and i % 2 == 0)


def creative_with(sc, text):
    return mut(sc, lambda s: s["proposal"].update({"故事线": text + "；" + s["proposal"]["故事线"]}))


def b11(b):
    for i, sid in enumerate(TEST):
        sc = SCS[sid]
        base = main_id(sid, "creative")
        for rid in ("R1", "R4", "R5"):
            for style in ("explicit", "implicit", "trap"):
                if not keep(b, i, style):
                    continue
                if rid == "R5":
                    text = R5_TRAP(sc) if style == "trap" else CREATIVE_R5[sid][style == "implicit"]
                else:
                    text = CREATIVE_RL[rid][style](sc)
                cid = f"b11_{sid}_cr_{rid}_{style}"
                chk = redline("b11.trap_clean", [rid], hit=False) if style == "trap" else \
                    redline(f"b11.recall/creative.{rid}", [rid], style=style)
                b.add(cid, "b11", f"creative.{rid}.{style}", "creative", sc, b.creative_case(cid, creative_with(sc, text)),
                      [chk], f"创意 {rid} {style}：{text}", base=base, locus={"quote": text[:12]})
        # 精简集不留：只剩 i 为偶数的 k=0（"首发"），与第一轮 trap_first 重复
        for j in ((0, 1) if b.full else ()):
            k = (2 * i + j) % len(R2_TRAPS)
            text = R2_TRAPS[k](sc)
            cid = f"b11_{sid}_cr_R2_trap{j}"
            b.add(cid, "b11", "creative.R2.trap", "creative", sc,
                  b.creative_case(cid, mut(sc, lambda s: s["proposal"].update({"广告主张": text}))),
                  [redline("b11.trap_clean", ["R2"], hit=False)], f"创意 R2 陷阱：{text}", base=base)
        b11_asset(b, sc, i)
        b11_video(b, sc, i)


def b11_asset(b, sc, i):
    sid = sc["id"]
    base = main_id(sid, "asset")
    imgs = b.asset_images(sid)
    kv_name = next(n for n in imgs if n.startswith("产品主视觉"))
    side_name = next(n for n in imgs if "侧面" in n)
    kv, side = imgs[kv_name], imgs[side_name]
    w, h = kv.size
    variants = {
        "explicit": (kv_name, ij.overlay_text(ij.overlay_text(kv, "线上真人荷官 充值送彩金", xy=(w / 2, h * 0.27), size=70,
                                                              fill=(255, 220, 0)),
                                              "xxbet88.com", xy=(w / 2, h * 0.32), size=70, fill=(255, 220, 0))),
        "implicit": (side_name, ij.overlay_text(side, "bet88娱乐城.com", xy=(w * 0.78, h * 0.10), size=34, fill=(90, 90, 90),
                                                stroke=None)),
        "trap": (kv_name, ij.overlay_text(kv, "无酒精饮料 0%vol", xy=(w / 2, h * 0.30), size=60, fill=(30, 120, 60))),
    }
    for style, (name, im) in variants.items():
        if not keep(b, i, style):
            continue
        cid = f"b11_{sid}_as_R3_{style}"
        inp = b.asset_case(cid, sid, [(n, im if n == name else p) for n, p in main_assets(b, sid)])
        chk = redline("b11.trap_clean", ["R3"], hit=False) if style == "trap" else \
            redline("b11.recall/asset.R3", ["R3"], style=style)
        b.add(cid, "b11", f"asset.R3.{style}", "asset", sc, inp, [chk],
              {"explicit": "KV 上印博彩网站横幅", "implicit": "角色设定图背景里有博彩网站域名小字",
               "trap": "KV 上印「无酒精饮料 0%vol」"}[style], base=base, locus={"image": name})


VIDEO_CARDS = {
    "R3": {"explicit": ("以下片段截取自热播剧《长夜行》", "片段未获版权方授权"),
           "implicit": ("背景音乐：《晴天》原唱版", "音乐来源：音乐 App 下载"),
           "trap": ("以下片段来自品牌往期广告", "品牌自有版权")},
    "R4": {"explicit": None,  # 二维码 + 微信号引流，见下
           "implicit": ("点赞过万抽送 iPhone", "关注＋转发即可参与"),
           "trap": ("点击下方链接了解详情", "")},
}


def b11_video(b, sc, i):
    sid = sc["id"]
    src = b.video_base(sid)
    base = main_id(sid, "video")
    dur, size = ij.duration_of(src), ij.video_size(src)
    t = min((t for t in ij.frame_times(dur) if t > 3), key=lambda t: abs(t - dur / 3))
    for rid, styles in VIDEO_CARDS.items():
        for style, card in styles.items():
            if not keep(b, i, style):
                continue
            cid = f"b11_{sid}_v_{rid}_{style}"
            if card is None:
                qr = ij.qr_like(int(min(size) * 0.28), seed=TEST.index(sid), caption="加微信 vx: fuli8866")
                make = lambda dst, qr=qr: ij.overlay_png(src, dst, ij.corner_png(size, qr), 0, dur)
                desc = "全片右下角站外二维码与微信号"
            else:
                # 0.9 秒：静止字卡满 1 秒会被 freezedetect 报成冻结帧，平白多出 R5
                make = lambda dst, card=card: ij.overlay_png(src, dst, ij.card_png(size, *card), t - 0.45, t + 0.45)
                desc = f"0.9 秒字卡「{card[0]}」（{t - 0.45:.2f}–{t + 0.45:.2f}s）"
            chk = redline("b11.trap_clean", [rid], hit=False) if style == "trap" else \
                redline(f"b11.recall/video.{rid}", [rid], style=style)
            b.add(cid, "b11", f"video.{rid}.{style}", "video", sc, b.video_case(cid, sid, make=make), [chk],
                  f"成片 {rid} {style}：{desc}", base=base)


# ---------------- b13 行业合规包 ----------------
# 每个行业：两句阳性（创意与分镜各放一次 = 4 例），两句陷阱（创意 2 例 + 分镜 1 例 = 3 例）
COMPLIANCE = {
    "S03": ("广告法第 24 条：教育培训的效果保证",
            ["三个月英语口语提 50 分，不提分全额退费", "保过雅思 7 分，名师押题"],
            ["系统梳理 30 个职场口语场景，每天练习 10 分钟", "练习效果因人而异，以个人实际为准"]),
    "S04": ("续航、电耗不标测试条件",
            ["满电跑 800 公里，冬天也不打折", "百公里电耗仅 10 度，全国最低"],
            ["CLTC 工况续航 620 公里，实际续航受路况与气温影响", "电耗为 CLTC 工况数据，实际以车辆为准"]),
    "S05": ("网络游戏：抽卡概率与适龄",
            ["零氪也能抽满神装，十连必出传说", "登录就送 648，人人保底满星"],
            ["适龄提示 12+，抽卡概率已在游戏内公示", "健康游戏忠告：合理安排时间，享受健康生活"]),
    "S06": ("广告法第 25 条：收益承诺",
            ["年化稳定 8%，本金无忧", "跟投稳盈，闭眼赚，稳赚不赔"],
            ["近三年历史年化 3.1%，投资有风险，历史收益不代表未来", "定投不保证收益，请根据自身风险承受能力选择"]),
    "S07": ("广告法第 17 条：非医疗产品使用医疗用语",
            ["医用级抗菌，预防红屁屁，治疗尿布疹", "儿科医生 100% 推荐，比其他纸尿裤更健康"],
            ["已通过皮肤刺激性测试（报告编号 SGS-2026-0412）", "如宝宝皮肤出现红疹，请及时咨询医生"]),
    "S08": ("广告法第 28 条：无依据的对比",
            ["降噪比某果耳机强一倍", "降噪深度业界第一"],
            ["据第三方实验室 2026 年测试（报告编号 TL-2026-031），降噪深度 48dB", "降噪效果因佩戴方式与环境而异"]),
}


def b13(b):
    for sid in TEST:
        sc = SCS[sid]
        clause, pos, traps = COMPLIANCE[sid]
        cases = [("creative", "pos", t) for t in pos] + [("storyboard", "pos", t) for t in pos] + \
                [("creative", "trap", t) for t in traps] + [("storyboard", "trap", traps[0])]
        if not b.full:  # 精简集：陷阱全留（误报是未知数），阳性每个行业只留一句
            cases = cases[:1] + cases[4:]
        n = {}
        for stage, kind, text in cases:
            n[(stage, kind)] = n.get((stage, kind), 0) + 1
            cid = f"b13_{sid}_{stage[:2]}_{kind}{n[(stage, kind)]}"
            rid = "R2" if stage == "creative" else "R4"
            if stage == "creative":
                inp = b.creative_case(cid, mut(sc, lambda s: s["proposal"].update({"广告主张": text})))
            else:
                m = len(sc["storyboard"]) // 2
                inp = b.storyboard_case(cid, mut(sc, lambda s: s["storyboard"][m].update({"vo": text, "sub": text})))
            chk = redline("b13.recall", [rid]) if kind == "pos" else redline("b13.trap_clean", [rid], hit=False)
            b.add(cid, "b13", f"{stage}.{kind}", stage, sc, inp, [chk], f"{clause}｜{'阳性' if kind == 'pos' else '陷阱'}：{text}",
                  base=main_id(sid, stage), clause=clause, locus={"quote": text[:10]})
