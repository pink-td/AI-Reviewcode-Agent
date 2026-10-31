# AI 代码审查平台（AI Code Review）

基于 Webhook 的自动化代码审查服务：开发者在 GitLab / GitHub / Gitea 上提交代码或发起
Merge Request 后，系统自动拉取 diff、调用大模型审查、把结果回写到 MR 评论，并支持多渠道
通知、落库统计与可视化看板，把 Code Review 的第一轮机械检查从人工转移到 AI。

> **来源声明**：本项目是在开源项目
> [`sunmh207/AI-Codereview-Gitlab`](https://github.com/sunmh207/AI-Codereview-Gitlab)
> （Apache-2.0）基础上做的**学习性复现与二次开发**，整体架构与主要功能源自原项目；
> 本人在其基础上完成了下述工程化改造与缺陷修复。原始版权归原作者所有，详见 `NOTICE`。

## 功能

- **多平台接入**：GitLab / GitHub / Gitea 的 Push、Merge Request / Pull Request 事件。
- **多模型可插拔**：DeepSeek、OpenAI、智谱、通义千问、Ollama、Anthropic Claude，
  通过工厂 + `BaseClient` 抽象，新增供应商只需一个类加一行注册。
- **自动回写**：审查结果直接回写到 MR/PR 的 Note / Review Comment。
- **多渠道通知**：钉钉、企业微信、飞书、自定义 Webhook。
- **自动化日报**：按 Commit 记录汇总每日开发进展，定时推送到 IM。
- **可视化看板**：Streamlit + pandas + matplotlib，按项目 / 人员维度统计审查记录与评分。
- **Agentic Review（可选）**：LLM 拥有工具调用能力（`read_file` / 沙箱 shell），
  可在本地克隆的代码库内自主探索，产出更全面的审查结果；任一阶段失败自动降级回 diff-only。

## 我在复现基础上做的事

> 以下为相对原项目的增量工作，也是这个仓库值得阅读的部分。

- **可靠性**：为所有 LLM / 平台 API 请求补齐 **timeout + 退避重试 + 分层降级**；
  修复「LLM 报错被当成审查结果返回」的问题，异常路径不再污染审查结论。
- **幂等并发**：在原「先查后写」的应用层幂等之上，补了数据库**唯一索引 + `IntegrityError` 捕获**，
  实测并发重复请求从 2 条记录收敛为 1 条，堵住「检查与落库之间调 LLM 数十秒」的 race condition。
- **Token 预算**：用 `tiktoken` 计数并在超限时截断，同时保留离线降级估算，避免内网无法下载词表时崩溃。
- **Agentic Review 模式**：实现仓库同步（clone 缓存 + 文件锁 + Token 注入 + `reset --hard` 幂等）、
  工具注册表与 Shell 沙箱（白名单 + 黑名单 + 路径越界 + 敏感文件 + 30s 超时五重校验），
  以及失败降级链路。
- **工程化**：结构化 JSON 日志（轮数 / 耗时 / token / 降级标记）、pytest 单测、
  Docker + supervisord 一容器双服务部署。

## 架构

```
api.py                 Flask API 入口（Webhook 接收）
ui.py                  Streamlit Dashboard 入口
biz/
├── api/routes/        webhook / dashboard / daily_report 路由
├── platforms/         gitlab / github / gitea 适配层
├── llm/               供应商工厂与各 client 实现
├── agent/              Agentic 审查：runner / tool_registry / safety / repo_syncer
├── service/           ReviewService（业务编排）
├── event/             blinker 事件总线
├── entity/            数据实体
└── utils/             日志、token、IM 通知、报表、代码解析
conf/                  配置模板、Prompt 模板、supervisord 配置
tests/                 单元与集成测试
```

事件流：

```
GitLab/GitHub/Gitea 事件
      │  webhook
      ▼
Flask 路由 ──校验/取 token/diff──► 子进程异步处理
                                      │
                          ┌───────────┼────────────┐
                          ▼           ▼            ▼
                    大模型审查   事件总线(blinker)  落库 SQLite
                                      │
                          ┌───────────┼────────────┐
                          ▼           ▼            ▼
                      回写评论    多渠道通知    可视化看板
```

## 快速开始

### Docker 部署

```bash
cp conf/.env.dist conf/.env     # 按需填写模型 Key、平台 Token、通知 Webhook
docker compose up -d --build
```

- API 服务：`http://<host>:5001`（Webhook 地址 `http://<host>:5001/review/webhook`）
- Dashboard：`http://<host>:5002`

### 本地 Python 部署（Python 3.10+）

```bash
pip install -r requirements.txt
cp conf/.env.dist conf/.env
python api.py
streamlit run ui.py --server.port=5002 --server.address=0.0.0.0
```

### 配置 Webhook

在 GitLab / GitHub / Gitea 项目的 Webhook 设置中：

- URL：`http://<host>:5001/review/webhook`
- 触发事件：Push、Merge Request / Pull Request
- Secret Token：可选，未在 `.env` 配置 `*_ACCESS_TOKEN` 时使用

## 配置说明

所有配置集中在 `conf/.env`，模板见 `conf/.env.dist`，主要包括：

| 分组 | 变量 | 说明 |
| --- | --- | --- |
| 模型 | `LLM_PROVIDER`、`*_API_KEY`、`*_API_BASE_URL`、`*_API_MODEL` | 选择供应商并填 Key |
| 审查 | `SUPPORTED_EXTENSIONS`、`REVIEW_MAX_TOKENS`、`REVIEW_STYLE` | 审查范围、Token 上限、审查风格 |
| Agentic | `REVIEW_STRATEGY`、`REPO_CACHE_DIR`、`AGENT_MAX_ITERATIONS` | 是否启用 agentic 模式 |
| 通知 | `DINGTALK_*`、`WECOM_*`、`FEISHU_*`、`EXTRA_WEBHOOK_*` | 各渠道开关与地址 |
| 平台 | `GITLAB_*`、`GITHUB_ACCESS_TOKEN`、`GITEA_*` | 代码托管平台凭据 |
| 看板 | `DASHBOARD_USER`、`DASHBOARD_PASSWORD` | 首次部署后请立即修改 |

## Agentic Review 模式

```bash
REVIEW_STRATEGY=agentic          # 默认 diff_only
REPO_CACHE_DIR=data/repo_cache   # 本地仓库缓存目录，需预留磁盘
AGENT_MAX_ITERATIONS=20          # 工具调用最大轮数
```

Shell 工具默认只允许读类命令，可通过 `AGENT_SHELL_ALLOWLIST` / `AGENT_SHELL_BLOCKLIST` 调整。
任意阶段（clone / fetch / LLM / 工具调用）失败都会自动降级回 `diff_only`。

## 测试

```bash
pytest
```

## 许可与致谢

- 本项目基于 [`sunmh207/AI-Codereview-Gitlab`](https://github.com/sunmh207/AI-Codereview-Gitlab)
  二次开发，遵循 **Apache License 2.0**，原始版权与许可声明见 `LICENSE` 与 `NOTICE`。
- 若你希望基于本项目继续开发，请同样保留原始版权与许可声明。

## 常见问题

见 [`doc/faq.md`](doc/faq.md)。
