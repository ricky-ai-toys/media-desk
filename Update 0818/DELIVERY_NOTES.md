# Media Desk 更新交付说明

> 基线：commit `a3a1cb0`（注：说明初版误写为 `e961899`，本仓库无此 commit，实际基线为 `a3a1cb0`）。交付为 5 个补丁 / 一个完整压缩包。
> 验证：**67 项 pytest 全部通过**（含 19 项新增契约测试）+ 前端 `tsc` 与 esbuild 构建通过。
> 未推 GitHub（连接器未授权）——应用方式见文末。

---

## 变更总览（对照四份审查报告的条目）

### Patch 0002 · PR-1 证据忠诚包

| 审查条目 | 实现 | 位置 |
|---|---|---|
| 实测报告 §二.1：coverage 5/15 vs TV 0·wire 0 同页打架 | 落库前 `_apply_evidence_overrides` 用 `agenda_evidence` 强制覆盖 `coverage`/`episode_count`/`source_file_count`，并写入 `evidence_programmes`；零证据 topic 进 warnings | `synth/weekly.py`、`analyze/evidence.py`（新增 `topic_programmes`） |
| 实测报告 §三：推断"引语"以原文排版展示 | `_ticker` 对每条 anchor question 做转写归一化比对，输出 `verified: bool`；前端未验证条目打 **paraphrase/转述** 标签 | `api/routes.py`、`web/src/views/BriefView.ts`、`lib/api.ts` |
| 实测报告 §四：LLM 自评 "confirmed" | `evidence_statuses` 改服务端规则推导（week_ahead 上限 supported，永不可 confirmed）；LLM 自评结果被整体替换 | `synth/weekly.py` |
| 报告一 §3：单次调用无重试、失败无痕 | `llm.chat` 3 次指数退避（1/4/16s）；`chat_json` 对非法 JSON 同样重试；原始 payload 落盘 `data/llm_raw/`；合成失败写 `status='synth_failed'` 的 edition 行 | `llm.py`、`synth/weekly.py`、`db.py` |
| 报告一 §4：pr_counsel 机械拼接 | 删除拼接兜底，缺字段置空 + warning；QC 新增 `pr_counsel_complete`（v2 阻断） | `synth/weekly.py`、`synth/qc.py` |
| 报告一 §2：figures_align 全局集合比较 + 硬编码排除项 | 改**逐字段递归成对比较**，差异写入 QC detail（如 `thesis: EN ['90'] vs ZH []`）；排除项动态生成（报告年/月/日）；**保持 v2 informational 属性**（尊重 README 设计意图，测试已锁定）；week_ahead 增加工作日约束 | `synth/qc.py` |
| 栏目报告 §六：双语平行性 | QC 新增 `interview_groups_parallel`、`question_group_items_parallel`（v2 阻断） | `synth/qc.py` |
| 实测报告 §七.4：坏源暴露 | `upsert_source` 尊重 yaml 的 enabled 标志（原硬编码 1，属 bug）；`sync_sources` 将 yaml 中移除/禁用的源置为 disabled；`source_health()` 默认只返回启用源 | `db.py` |
| 实测报告 §七.4：内部 pipeline 状态公开 | `/api/meta` 的 pipeline 只留 stage/status/updated_at | `api/routes.py` |

### Patch 0003 · PR-2 CNBC 源扩容

- `config/sources.yaml` 新增 3 个 CNBC 候选源：**Squawk Box Asia、The China Connection、Street Signs Asia**，`enabled: false`。
- 新增 `scripts/verify_sources.py`：在服务器上（需 YouTube 可达）用 yt-dlp 验证播放列表解析、标题正则命中、字幕可得性，GO 之后才改 `enabled: true`。**本沙箱无法访问 YouTube，故未直接启用**——这是有意的保守设计，不是遗漏。
- 样本框披露：合成 prompt 注入当周实际监测节目清单并要求 `monitored_outlets` 如实反映；PDF 方法学附录新增 Sample frame 声明段。

### Patch 0004 · PR-3 口径与一致性

- **`synth/report_spec.py`（新）**：数量区间/枚举词表/字数预算单一事实源；`weekly.py` 的 SYSTEM 由它渲染、`qc.py` 的全部阈值改从它读取——22 vs 24 词漂移类问题从结构上消除。
- 邮件 momentum 徽标修复：原读 `direction`（v2 不存在）导致全部显示 "Stable"，现回退链 `direction → momentum → stable`；实测渲染输出 accelerating/rising/stable/fading。
- 邮件新增 **Week ahead** 板块（EN，空则整块不渲染）+ **延续观察清单**（ZH watchlist，此前缺失）；删除与 hero 重复的 "In one sentence" 框。
- lifecycle：链接需 overlap≥0.5 **且**交集词≥3（治短标题误并/断链）；单点 fading 的 phase 不再显示 "new"。fixture 回放验证：3 条跨周话题正确成链。
- comms 卡片 teaser 与正文重复时隐藏正文。

### Patch 0001/0005 · 测试基建与文档

- `scripts/make_fixture_db.py`：合成 fixture（2 期、40 episodes、60 articles），`conftest.py` 自动构建——测试从此脱离生产库。
- 新增 `tests/test_synthesis_integrity.py`（16 项契约测试）与 `tests/test_lifecycle.py`（3 项）。
- README 更新（测试、源验证、report_spec 说明）。

---

## 有意未做（Follow-ups）

embedding 问题聚类、canonical topic ID、share of voice/嘉宾结构/实体提及新栏目、golden set 抽检、CNBC 源启用（待服务器验证）、`_figures_align` 升级为 blockable（当前 informational + 差异可见，观察误报率后再定）。

## 应用方式

```bash
# 方式 A：补丁序列（保留审查粒度）
cd ~/workspace/media-desk && git am /path/to/patches/*.patch

# 方式 B：整包覆盖（无 git 历史）
unzip media-desk-updated.zip -d ~/workspace/media-desk

# 之后
cd ~/workspace/media-desk
.venv/bin/python -m pytest tests/ -q        # 应为 67 passed
cd web && npm install && npm run build      # dist 若被 gitignore 需重建
```

## 上线后验证清单（服务器上）

1. `scripts/verify_sources.py cnbc_squawk_box_asia` → GO 后启用对应源
2. `scripts/resynth_weeks.py --edition 2026-08-10_to_2026-08-14`（需 DEEPSEEK_API_KEY）重合成最新期 → 确认 `coverage` 变为真实值、Wire vs TV 不再打架、`evidence_statuses` 为规则标签
3. 检查 `data/llm_raw/` 有落盘文件；邮件导出确认 momentum 徽标不再全 "Stable"
