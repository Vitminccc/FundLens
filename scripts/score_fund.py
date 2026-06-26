# -*- coding: utf-8 -*-
"""一键：给任意基金准备好「双层评分」所需的全部材料。
自动完成：解析代码 → 备齐数据 → 计算全部量化指标 → 输出双层评分档案：
  第一层：综合质量评分（7维，纯量化自动计算）
  第二层：郑希风格契合度证据档案（6维，AI 逐维打分）
  附加：市场模式 + 4种买点信号 + 行业归一化

用法:
  python scripts/score_fund.py 005827
  python scripts/score_fund.py 中欧医疗健康
  python scripts/score_fund.py 001513          # 郑希自己的基金，用精编快照

研究与学习辅助，非投资建议。
"""
import os, sys, json, glob, datetime
import fetch_fund_data as F
import fetch_any_fund as A

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ZX_DIR = os.path.join(ROOT, "references", "fund_data")
CACHE = os.path.join(ROOT, "references", "fund_data_cache")
LIST = os.path.join(ROOT, "references", "all_funds", "fund_list.json")

# ── 头部基金公司名单（基金经理维度加成用） ──
TOP_FUND_COMPANIES = {
    "易方达", "华夏", "广发", "南方", "富国", "嘉实", "招商", "汇添富",
    "博时", "鹏华", "工银瑞信", "兴证全球", "中欧", "景顺长城", "交银施罗德",
}

# ── 分析周期加权表 ──
PERIOD_WEIGHTS = {
    "7d":   [("7d", 0.60), ("30d", 0.30), ("90d", 0.10)],
    "30d":  [("30d", 0.40), ("90d", 0.25), ("180d", 0.20), ("365d", 0.15)],
    "90d":  [("90d", 0.40), ("180d", 0.30), ("365d", 0.20), ("30d", 0.10)],
    "180d": [("180d", 0.40), ("365d", 0.35), ("90d", 0.15), ("730d", 0.10)],
    "365d": [("365d", 0.45), ("730d", 0.25), ("180d", 0.15), ("1095d", 0.15)],
}

# ── 市场模式权重切换 ──
MARKET_MODE_WEIGHTS = {
    "均衡": {"收益能力": 25, "风险控制": 20, "收益质量": 15, "赚钱效应": 10},
    "牛市": {"收益能力": 35, "风险控制": 10, "收益质量": 15, "赚钱效应": 10},
    "熊市": {"收益能力": 15, "风险控制": 30, "收益质量": 20, "赚钱效应": 5},
}

DAY_MAP = {"7d": 7, "30d": 30, "90d": 90, "180d": 180, "365d": 365, "730d": 730, "1095d": 1095}


# ═══════════════════════════════════════════
# 解析与数据加载
# ═══════════════════════════════════════════

def resolve(arg):
    """把代码或名称解析成 (code, name, type)。"""
    if not os.path.exists(LIST):
        return arg, arg, ""
    funds = json.load(open(LIST, encoding="utf-8"))["funds"]
    if arg.isdigit():
        for f in funds:
            if f["code"] == arg:
                return f["code"], f["name"], f["type"]
        return arg, arg, ""
    cands = [f for f in funds if arg in f["name"] or arg.upper() in f["abbr"] or arg.upper() in f["pinyin"]]
    if not cands:
        return None, arg, ""
    cands.sort(key=lambda f: len(f["name"]))
    return cands[0]["code"], cands[0]["name"], cands[0]["type"]


def find_data_dir(code):
    """优先郑希精编快照，其次缓存。"""
    for base in (ZX_DIR, CACHE):
        hit = glob.glob(os.path.join(base, f"{code}_*"))
        if hit and os.path.exists(os.path.join(hit[0], "季度持仓.json")):
            return hit[0], (base == ZX_DIR)
    return None, False


# ═══════════════════════════════════════════
# 量化计算函数
# ═══════════════════════════════════════════

def period_return(ac, days):
    """从累计净值序列计算近 days 天收益率%。"""
    if not ac or len(ac) < 2:
        return None
    last_ts, last_v = ac[-1]
    target = last_ts - days * 86400 * 1000
    base = None
    for ts, v in ac:
        if ts >= target:
            base = v
            break
    if not base or base == 0:
        base = ac[0][1]
    if not base or base == 0:
        return None
    return round((last_v / base - 1) * 100, 2)


def period_weighted_return(ac, period="90d"):
    """按分析周期加权收益率，返回 (加权收益率%, 各时段明细)。"""
    weights = PERIOD_WEIGHTS.get(period, PERIOD_WEIGHTS["90d"])
    details = {}
    weighted = 0.0
    total_w = 0.0
    for key, w in weights:
        days = DAY_MAP.get(key, 90)
        r = period_return(ac, days)
        if r is not None:
            details[key] = r
            weighted += r * w
            total_w += w
    if total_w == 0:
        return None, details
    return round(weighted / total_w, 2), details


def period_weighted_score(ac, period="90d"):
    """加权收益率 → 0-25 分。映射：≥100%→25, 0%→12.5, ≤-50%→0，线性插值。"""
    wr, _ = period_weighted_return(ac, period)
    if wr is None:
        return 0, None, {}
    if wr >= 100:
        score = 25
    elif wr >= 0:
        score = 12.5 + wr / 100 * 12.5
    elif wr >= -50:
        score = (wr + 50) / 50 * 12.5
    else:
        score = 0
    _, details = period_weighted_return(ac, period)
    return round(score, 1), wr, details


def max_drawdown_1y(ac):
    """近1年最大回撤%。"""
    if not ac or len(ac) < 2:
        return None
    last_ts = ac[-1][0]
    cutoff = last_ts - 365 * 86400 * 1000
    subset = [(ts, v) for ts, v in ac if ts >= cutoff]
    if len(subset) < 2:
        return F.max_drawdown(ac)
    return F.max_drawdown(subset)


def risk_control_score(mdd_1y):
    """最大回撤 → 0-20 分。0%回撤=20分，50%+回撤=0分，线性映射。"""
    if mdd_1y is None:
        return 0
    mdd_abs = abs(mdd_1y)
    if mdd_abs <= 0:
        return 20
    if mdd_abs >= 50:
        return 0
    return round(20 * (1 - mdd_abs / 50), 1)


def calmar_ratio(ac):
    """年化收益 ÷ |最大回撤|。返回 calmar 值。"""
    if not ac or len(ac) < 2:
        return None
    mdd = F.max_drawdown(ac)
    if mdd is None or mdd >= 0:
        return None  # 无回撤时返回 None
    mdd_abs = abs(mdd)
    # 年化收益
    first_ts, first_v = ac[0]
    last_ts, last_v = ac[-1]
    years = (last_ts - first_ts) / (365.0 * 86400 * 1000)
    if years < 0.1 or first_v <= 0:
        return None
    total_ret = last_v / first_v - 1
    annual_ret = (1 + total_ret) ** (1 / years) - 1
    return round(annual_ret / max(mdd_abs / 100, 0.001), 2)


def quality_score(calmar):
    """卡玛比率 → 0-15 分。≥3→15, 0→5, <0→0。"""
    if calmar is None:
        return 5.0  # 无数据给中间分
    if calmar >= 3:
        score = 15
    elif calmar >= 0:
        score = 5 + calmar / 3 * 10
    else:
        score = max(0, 5 + calmar)
    return round(min(15, max(0, score)), 1)


def positive_return_prob(nwt):
    """从单位净值走势计算月/季/半年/年正收益概率。
    返回 (加权概率%, 各期明细)。"""
    if not nwt or len(nwt) < 2:
        return None, {}
    # 按日分组 equityReturn
    last_ts = nwt[-1]["x"]
    periods = {
        "月": 30 * 86400 * 1000,
        "季": 90 * 86400 * 1000,
        "半年": 180 * 86400 * 1000,
        "年": 365 * 86400 * 1000,
    }
    weights = [0.1, 0.2, 0.3, 0.4]
    details = {}
    probs = []
    for (name, ms), w in zip(periods.items(), weights):
        cutoff = last_ts - ms
        subset = [p for p in nwt if p["x"] >= cutoff and p.get("equityReturn") is not None]
        if not subset:
            details[name] = None
            probs.append(0.5)  # 无数据给中间值
            continue
        positive = sum(1 for p in subset if p["equityReturn"] > 0)
        ratio = positive / len(subset) * 100
        details[name] = round(ratio, 1)
        probs.append(ratio / 100)
    weighted_prob = sum(p * w for p, w in zip(probs, weights))
    return round(weighted_prob * 100, 1), details


def earning_effect_score(nwt):
    """正收益概率 → 0-10 分。100%→10, 50%→5, 0%→0。"""
    prob, details = positive_return_prob(nwt)
    if prob is None:
        return 5.0, None, {}
    score = prob / 10  # 0-100 → 0-10
    return round(score, 1), prob, details


def style_drift_score(ac, short=90, long_days=365):
    """收益一致性 + 风格漂移 → 0-10 分。
    一致性(60%)：短期方向与长期方向一致 → 高分
    漂移(40%)：短长期收益率差距越小 → 高分"""
    if not ac or len(ac) < 2:
        return 5.0, None
    short_ret = period_return(ac, short)
    long_ret = period_return(ac, long_days)
    if short_ret is None or long_ret is None:
        return 5.0, None

    # 一致性：方向一致得满分，反向得0分
    if (short_ret >= 0 and long_ret >= 0) or (short_ret < 0 and long_ret < 0):
        consistency = 100
    else:
        consistency = 0

    # 漂移度：差距越小越好
    drift = abs(short_ret - long_ret) / max(abs(long_ret), 0.01)
    if drift <= 0.2:
        drift_score = 100
    elif drift >= 2.0:
        drift_score = 0
    else:
        drift_score = (2.0 - drift) / 1.8 * 100

    total = consistency * 0.6 + drift_score * 0.4
    score = total / 100 * 10
    info = {"short_ret": short_ret, "long_ret": long_ret,
            "consistency": consistency, "drift": round(drift, 2)}
    return round(score, 1), info


def turnover_proxy(quarters):
    """季度间换手代理：近5季相邻前十大重叠外平均换手%。"""
    qs = sorted(quarters, key=lambda q: (q["year"], q["quarter"]))
    qs = qs[-5:]
    diffs = []
    for a, b in zip(qs, qs[1:]):
        sa = {h["股票代码"] for h in a["holdings"]}
        sb = {h["股票代码"] for h in b["holdings"]}
        if sa and sb:
            overlap = len(sa & sb) / max(len(sb), 1)
            diffs.append(1 - overlap)
    return round(sum(diffs) / len(diffs) * 100, 1) if diffs else None


def detect_market_mode():
    """判断当前市场模式：牛市/熊市/均衡。
    沪深300 60日收益 > +15% = 牛市，< -10% = 熊市，否则均衡。"""
    kline = F.fetch_index_kline("000300", 120)
    if not kline or len(kline) < 60:
        return "均衡", None
    # 近60日收益率
    recent = kline[-60:]
    ret = (recent[-1][1] / recent[0][1] - 1) * 100
    if ret > 15:
        return "牛市", round(ret, 2)
    elif ret < -10:
        return "熊市", round(ret, 2)
    else:
        return "均衡", round(ret, 2)


def compute_ratings_score(ratings):
    """4机构评级 → 0-10 分。均值映射0-7 + 5星加成0-3。无评级给5/10。"""
    if not ratings:
        return 5.0, "无评级数据"
    avg = ratings.get("avg_star")
    if avg is None:
        return 5.0, "无评级数据"
    # 均值 1-5 映射到 0-7
    base = (avg - 1) / 4 * 7
    # 5星数量加成 0-3
    five_count = ratings.get("five_star_count", 0)
    bonus = min(five_count * 1.0, 3.0)
    score = base + bonus
    parts = []
    for name in ["招商证券", "上海证券3年", "上海证券5年", "济安金信", "晨星"]:
        v = ratings.get(name)
        if v is not None:
            parts.append(f"{name}{v}★")
    desc = f"均值{avg}星({', '.join(parts)})"
    return round(min(10, max(0, score)), 1), desc


def compute_manager_score(pz):
    """基金经理 → 0-10 分。1人管理=7分(专注)，头部基金公司+3分。"""
    fm = pz.get("基金经理") or []
    if not isinstance(fm, list) or not fm:
        return 5.0, "无经理数据"
    count = len(fm)
    if count == 1:
        base = 7
    elif count == 2:
        base = 5
    else:
        base = 3
    # 检查基金公司是否头部
    company = ""
    bonus = 0
    # 从经理信息中尝试获取公司
    for m in fm:
        name = m.get("name", "")
        # 经理名不含公司信息，从基金名称推断
        break

    # 从基金名称推断公司
    fund_name = pz.get("fS_name", "")
    company_bonus = 0
    for comp in TOP_FUND_COMPANIES:
        if comp in fund_name:
            company = comp
            company_bonus = 3
            break
    score = round(min(10, base + company_bonus), 1)
    desc = f"{count}人管理"
    if company:
        desc += f"，{company}(头部加成)"
    return round(min(10, score), 1), desc


def check_buy_signals(total_score, mdd_1y, nwt, earning_pct, risk_weight):
    """4种买点信号检测。返回 {信号名: (bool, 说明)}。"""
    signals = {}

    # 回撤买点：近1年最大回撤 ≥ 10%
    if mdd_1y is not None and abs(mdd_1y) >= 10:
        signals["回撤买点"] = (True, f"近1年最大回撤 {abs(mdd_1y)}%>=10%")
    else:
        signals["回撤买点"] = (False, f"近1年最大回撤 {abs(mdd_1y)}%" if mdd_1y is not None else "无回撤数据")

    # AI买点（优先判断，与评分买点互斥）
    ai_trigger = (total_score >= 70 and earning_pct is not None and earning_pct >= 80
                  and risk_weight is not None and risk_weight < 50)
    if ai_trigger:
        signals["AI买点"] = (True, f"评分{total_score}+赚钱效应{earning_pct}%+风控权重{risk_weight}%")
        signals["评分买点"] = (False, f"综合评分 {total_score}（AI买点已触发，互斥）")
    else:
        signals["AI买点"] = (False, "条件未满足")
        # 评分买点
        if total_score >= 80:
            signals["评分买点"] = (True, f"综合评分 {total_score}≥80")
        else:
            signals["评分买点"] = (False, f"综合评分 {total_score}")

    # 连跌买点：连续3日下跌 或 单日跌幅>2%
    if nwt and len(nwt) >= 3:
        recent = nwt[-3:]
        all_down = all(p.get("equityReturn") is not None and p["equityReturn"] < 0 for p in recent)
        last_day = nwt[-1].get("equityReturn")
        big_drop = last_day is not None and last_day < -2
        if all_down:
            signals["连跌买点"] = (True, "近3个交易日连续下跌")
        elif big_drop:
            signals["连跌买点"] = (True, f"当日跌幅 {round(last_day, 2)}%>2%")
        else:
            last_ret = round(last_day, 2) if last_day is not None else None
            signals["连跌买点"] = (False, f"近3日未连续下跌，今日涨幅{last_ret}%")
    else:
        signals["连跌买点"] = (False, "净值数据不足")

    return signals


def industry_percentile(pz):
    """用同类排名走势算最新百分位排名。返回 (百分位, 同类总数) 或 (None, None)。"""
    rank_data = pz.get("同类排名走势") or []
    if not rank_data:
        return None, None
    latest = rank_data[-1]
    rank = latest.get("y")
    total = latest.get("sc")
    if rank is None or total is None:
        return None, None
    try:
        rank = int(rank)
        total = int(total)
    except (ValueError, TypeError):
        return None, None
    if total <= 0:
        return None, None
    pct = round((1 - rank / total) * 100, 1)
    return pct, total


# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/score_fund.py <基金代码或名称> [分析周期:7d/30d/90d/180d/365d]")
        return
    arg = sys.argv[1]
    period = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in PERIOD_WEIGHTS else "90d"

    code, name, ftype = resolve(arg)
    if not code:
        print(f"没找到「{arg}」。试试 python scripts/fund_lookup.py {arg}")
        return

    d, is_zx = find_data_dir(code)
    if not d:
        print(f"本地无 {code} 数据，实时抓取中 ...")
        A.fetch_one(code)
        d, is_zx = find_data_dir(code)
    if not d:
        print(f"抓取失败，无法评分 {code} {name}")
        return

    quarters = json.load(open(os.path.join(d, "季度持仓.json"), encoding="utf-8"))
    pzp = os.path.join(d, "净值业绩规模.json")
    pz = json.load(open(pzp, encoding="utf-8")) if os.path.exists(pzp) else {}

    # ── 数据准备 ──
    ac = [p for p in (pz.get("累计净值走势") or []) if p and len(p) >= 2 and p[1] is not None]
    nwt = [p for p in (pz.get("单位净值走势") or []) if isinstance(p, dict) and p.get("y") is not None]

    # 市场模式（一次运行只判断一次）
    mode, mode_ret = detect_market_mode()

    # 4机构评级
    ratings = F.fetch_ratings(code)

    # ══════════════════════════════════════════
    # 第一层：综合质量评分（7维，纯量化）
    # ══════════════════════════════════════════

    # 1. 收益能力 (25分)
    earn_score, earn_wr, earn_details = period_weighted_score(ac, period)

    # 2. 风险控制 (20分)
    mdd_1y = max_drawdown_1y(ac)
    risk_score = risk_control_score(mdd_1y)

    # 3. 收益质量 (15分)
    calmar = calmar_ratio(ac)
    qual_score = quality_score(calmar)

    # 4. 基金评级 (10分)
    rating_score, rating_desc = compute_ratings_score(ratings)

    # 5. 基金经理 (10分)
    mgr_score, mgr_desc = compute_manager_score(pz)

    # 6. 持仓质量 (10分)
    hold_score, hold_info = style_drift_score(ac)

    # 7. 赚钱效应 (10分)
    effect_score, effect_pct, effect_details = earning_effect_score(nwt)

    # ── 原始总分 ──
    raw_scores = {
        "收益能力": earn_score,
        "风险控制": risk_score,
        "收益质量": qual_score,
        "基金评级": rating_score,
        "基金经理": mgr_score,
        "持仓质量": hold_score,
        "赚钱效应": effect_score,
    }
    raw_total = sum(raw_scores.values())

    # ── 市场模式加权总分 ──
    mode_weights = MARKET_MODE_WEIGHTS.get(mode, MARKET_MODE_WEIGHTS["均衡"])
    mode_weighted_total = 0
    for dim in ["收益能力", "风险控制", "收益质量", "赚钱效应"]:
        base_max = {"收益能力": 25, "风险控制": 20, "收益质量": 15, "赚钱效应": 10}[dim]
        new_max = mode_weights.get(dim, base_max)
        mode_weighted_total += raw_scores[dim] / base_max * new_max if base_max > 0 else 0
    # 不受市场模式影响的维度直接加
    mode_weighted_total += raw_scores["基金评级"] + raw_scores["基金经理"] + raw_scores["持仓质量"]

    # ── 行业归一化 ──
    pct, peer_total = industry_percentile(pz)
    normalized = round(pct / 100 * mode_weighted_total, 1) if pct is not None else None

    # ── 风险控制权重占比（买点信号用） ──
    risk_weight_pct = round(risk_score / 20 * 100, 1) if risk_score else None

    # ── 买点信号 ──
    signals = check_buy_signals(
        round(mode_weighted_total, 1), mdd_1y, nwt, effect_pct, risk_weight_pct
    )

    # ══════════════════════════════════════════
    # 输出
    # ══════════════════════════════════════════

    print("=" * 70)
    print(f"郑希框架 · 双层评分 · 证据档案")
    print(f"基金：{name}（{code}）  类型：{ftype}")
    print(f"市场模式：{mode}" + (f"（沪深300近60日 {mode_ret}%）" if mode_ret is not None else ""))
    print(f"数据来源：{'郑希精编快照' if is_zx else '全市场实时缓存'}（{os.path.relpath(d, ROOT)}）")
    print(f"分析周期：{period}")
    print("=" * 70)

    # ── 第一层：综合质量评分 ──
    print(f"\n{'━' * 50}")
    print(f"【第一层：综合质量评分 · 自动计算】")
    print(f"{'━' * 50}")
    print(f"  1. 收益能力：{earn_score}/25  (加权收益率 {earn_wr}%)")
    if earn_details:
        for k, v in earn_details.items():
            print(f"     · 近{DAY_MAP.get(k,'?')}天：{v}%")
    print(f"  2. 风险控制：{risk_score}/20  (近1年最大回撤 {mdd_1y}%)")
    print(f"  3. 收益质量：{qual_score}/15  (卡玛比率 {calmar})")
    print(f"  4. 基金评级：{rating_score}/10  ({rating_desc})")
    print(f"  5. 基金经理：{mgr_score}/10  ({mgr_desc})")
    print(f"  6. 持仓质量：{hold_score}/10  ", end="")
    if hold_info:
        print(f"(短{hold_info['short_ret']}% vs 长{hold_info['long_ret']}%，一致性{hold_info['consistency']}%，漂移{hold_info['drift']})")
    else:
        print("(数据不足)")
    print(f"  7. 赚钱效应：{effect_score}/10  (正收益概率 {effect_pct}%)")
    if effect_details:
        for k, v in effect_details.items():
            print(f"     · {k}正收益：{v}%")
    print(f"  {'─' * 40}")
    print(f"  原始总分：{round(raw_total, 1)}/100")
    print(f"  {mode}模式加权：{round(mode_weighted_total, 1)}/100")
    if normalized is not None:
        print(f"  同类归一化：{normalized}/100（同类{peer_total}只，百分位{pct}%）")
    else:
        print(f"  同类归一化：(新基金，同类数据不足，未归一化)")

    # ── 买点信号 ──
    print(f"\n{'━' * 50}")
    print(f"【买点信号】")
    print(f"{'━' * 50}")
    for sig, (triggered, desc) in signals.items():
        mark = "✓" if triggered else "✗"
        print(f"  {mark} {sig}：{desc}")

    # ── 第二层：郑希风格契合度证据档案 ──
    print(f"\n{'━' * 50}")
    print(f"【第二层：郑希风格契合度 · 证据档案】")
    print(f"{'━' * 50}")
    print(f"  → 请按 references/scorecard.md Part A 逐维打分\n")

    # 最新一季前十大
    if quarters:
        latest = sorted(quarters, key=lambda q: (q["year"], q["quarter"]))[-1]
        conc = sum(float(h["占净值比"].rstrip("%")) for h in latest["holdings"]
                   if h["占净值比"].rstrip("%").replace(".", "").isdigit())
        print(f"  【最新前十大持仓】{latest['year']}年第{latest['quarter']}季度  (前十大合计约 {round(conc,1)}% 净值)")
        for i, h in enumerate(latest["holdings"], 1):
            print(f"    {i:2d}. {h['股票名称']}（{h['股票代码']}） {h['占净值比']}")
        print(f"\n  【集中度】前十大合计 ≈ {round(conc,1)}%（越高越集中）")
        tp = turnover_proxy(quarters)
        print(f"  【换手代理】近5季相邻重叠外的平均换手 ≈ {tp}%（越高=调仓越频繁=越像周期拼接）")
        print(f"  【披露季度数】{len(quarters)} 个季度（可看历史主线如何切换）")

    # 业绩/规模/配置
    if pz:
        if ac:
            print(f"\n  【业绩（按累计净值估算）】")
            print(f"    今年以来 {F.year_return(ac)}% | 近1年 {F.window_return(ac,365)}% | "
                  f"近3年 {F.window_return(ac,365*3)}% | 成立以来 {round((ac[-1][1]/ac[0][1]-1)*100,2)}%")
            print(f"    最大回撤（成立以来） {F.max_drawdown(ac)}% | 近1年最大回撤 {mdd_1y}%")
            print(f"    卡玛比率 {calmar}")
        gt = pz.get("累计收益率走势") or []
        if gt and gt[0].get("data"):
            rng = gt[0]["data"]
            print(f"    区间对比（{F.fmt_ts(rng[0][0])}~{F.fmt_ts(rng[-1][0])}）：" +
                  " | ".join(f"{s['name']} {s['data'][-1][1]}%" for s in gt if s.get("data")))
        fs = pz.get("规模变动") or {}
        if isinstance(fs, dict) and fs.get("series"):
            last = fs["series"][-1]
            print(f"  【规模】最新 {last.get('y')} 亿元（{fs['categories'][-1]}）")
        aa = pz.get("资产配置") or {}
        if isinstance(aa, dict) and aa.get("series"):
            parts = [f"{s['name']} {s['data'][-1]}%" for s in aa["series"] if s.get("data") and "占" in (s.get("name") or "")]
            if parts:
                print(f"  【资产配置】{aa['categories'][-1]}：" + "；".join(parts))
        fm = pz.get("基金经理") or []
        for m in (fm if isinstance(fm, list) else []):
            prof = m.get("profit") or {}
            ser = (prof.get("series") or [{}])[0].get("data") if prof.get("series") else None
            if prof.get("categories") and ser:
                print(f"  【现任经理任职回报】{m.get('name')}：" +
                      "；".join(f"{c} {x.get('y')}%" for c, x in zip(prof["categories"], ser)))
        pe = pz.get("业绩评价") or {}
        if isinstance(pe, dict) and isinstance(pe.get("data"), list):
            print("  【天天基金五维(满分100)】" + "；".join(f"{c}{v}" for c, v in zip(pe.get("categories", []), pe["data"])))

        # 同类百分位
        if pct is not None:
            print(f"  【同类排名】{pct}% 百分位（同类{peer_total}只）")

    # ── 双层评分桥接说明 ──
    print(f"\n{'━' * 50}")
    print(f"【双层评分交互解读】")
    print(f"{'━' * 50}")
    quality_level = "高" if mode_weighted_total >= 70 else ("中" if mode_weighted_total >= 45 else "低")
    print(f"  综合质量：{quality_level}（{round(mode_weighted_total, 1)}/100）")
    print(f"  郑希风格：待 AI 按 scorecard.md Part A 打分")
    print(f"  ─")
    print(f"  提示：风格契合度衡量「像不像郑希会买的」，综合质量衡量「这只基金本身好不好」。")
    print(f"  低契合度 ≠ 差基金，可能只是风格与郑希不同（如防御型/红利/纯债基金）。")

    print("\n" + "=" * 70)
    print("下一步：")
    print("  1. 按 references/scorecard.md Part A 给郑希风格契合度逐维打分")
    print("  2. 按输出模板合成双层评分报告")
    print("提醒：综合质量评分已自动计算；风格契合度需 AI 判断；个股 ROE/流动性标「需核实」")
    print("      本评分非基金优劣判断，亦非投资建议。")
    print("=" * 70)


if __name__ == "__main__":
    main()
