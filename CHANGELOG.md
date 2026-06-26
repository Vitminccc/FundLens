# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-06-26

### Added
- **双层评分体系**：Part A 郑希风格契合度（6维AI打分）+ Part B 综合质量评分（7维量化自动计算）
- **7维综合质量评分**：收益能力/风险控制/收益质量/基金评级/基金经理/持仓质量/赚钱效应，满分100
- **5种分析周期**加权收益率：7d/30d/90d/180d/365d，可按投资期限切换
- **3种市场模式**权重切换：牛市/熊市/均衡，自动检测沪深300近60日收益
- **4种买点信号**：回撤买点/评分买点/连跌买点/AI买点
- **行业归一化**：利用同类排名走势计算百分位，跨类型基金可比
- **4机构评级**抓取：上海证券/招商证券/济安金信/晨星（天天基金API）
- **市场模式自动检测**：基于沪深300指数K线数据
- `fetch_index_kline()` 函数：抓取指数日K线数据
- `fetch_ratings()` 函数：抓取4机构基金评级
- `requirements.txt`：显式声明 Python 依赖
- `skill.yml`：WorkBuddy 技能清单
- `CHANGELOG.md`：版本变更记录

### Changed
- `score_fund.py`：大幅重写，从单一证据档案输出升级为双层评分+买点信号+市场模式+归一化的完整评分报告
- `scorecard.md`：从6维郑希框架评分卡重写为双层评分卡（Part A + Part B + 市场模式 + 买点信号 + 交互规则 + 输出模板）
- `SKILL.md`：YAML description 扩展双层评分/买点信号/市场模式描述；评分章节改为"双层评分"
- `README.md`：功能表新增综合质量/买点信号行；示例更新为双层输出；脚本速查表新增分析周期参数

## [1.0.0] - 2026-06-19

### Added
- 郑希观点库初始版本
- 溯源问答：基于 2012–2026 全部公开观点语料
- 投资方法框架：从语料蒸馏，每条有本人原话佐证
- 前瞻应用：语料未覆盖话题可用方法推演
- 风格化点评：模仿郑希季报/手记口吻
- 言行对照：8只基金真实数据（持仓/净值/业绩/规模/任职回报）
- 全市场基金查询：约2.7万只基金列表 + 按需实时抓取
- 郑希框架6维评分卡
- 7个脚本：search_corpus / build_index / fetch_fund_data / build_fund_list / fund_lookup / fetch_any_fund / score_fund
