# 贡献指南

感谢你对郑希观点库的关注！欢迎贡献。

## 如何贡献

### 报告问题

- 在 [Issues](../../issues) 中提交 bug 或功能建议
- 请描述：预期行为 vs 实际行为、复现步骤、运行环境

### 提交代码

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'feat: add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

### 代码规范

- Python 脚本保持与现有风格一致
- 脚本调用方式保持"单条命令"模式（不使用 `cd &&`、管道、重定向）
- 新增脚本需在 `SKILL.md` 和 `README.md` 中同步更新说明

### 语料更新

- 新增语料放入 `references/corpus/` 对应子目录（定期报告/基金经理手记/媒体报道）
- 运行 `python scripts/build_index.py` 重建索引
- 确保语料为郑希**公开披露**的内容，注明出处和日期

### 数据刷新

- 郑希基金数据：`python scripts/fetch_fund_data.py`
- 全市场基金列表：`python scripts/build_fund_list.py`
- 注意：`fund_data_cache/` 和 `fund_list.json` 已在 `.gitignore` 中，不要提交到仓库

## 重要原则

- **不杜撰**：不编造郑希没说过的话，不捏造持仓/业绩数字
- **忠于原文**：引用必须与语料一致，不缩写后冒充原话
- **分清三层**：原话 vs 推演 vs 需核实的事实，读者要能分辨
- **非投资建议**：所有内容为研究与学习辅助

## License

贡献的代码和内容遵循 [MIT License](LICENSE)。
