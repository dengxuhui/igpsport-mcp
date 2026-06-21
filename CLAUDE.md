# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 详细工程蓝图、开发计划与协议逆向笔记保存在**本地工作文档**(未随仓库提交)。本文件是面向贡献者的稳定速查 + 设计红线。

## 项目定位

一个本地运行的 **MCP server**,把 iGPSport 骑行数据接入 LLM 客户端(Claude Desktop / Claude Code 等),让用户用自然语言分析训练数据。差异化:**派生训练指标(NP/IF/TSS/CTL/ATL/TSB)在 MCP 层算好返回**,LLM 拿到的是可直接讲故事的数字,而非原始 stream。

本地 stdio 部署,不做 remote;数据不外流。

## 不要做的事(已决策,勿回头)

任何"好心"的反向建议都应被拒绝:

- ❌ **不加 Web UI / dashboard**——走纯 MCP stdio,复用 LLM 客户端的对话界面。
- ❌ **不用 TypeScript**——选 Python 是因为 `fitparse` / `pandas` / 官方 `mcp` SDK。
- ❌ **不做** remote MCP、多账号、训练计划生成(v2)、导出 .fit/.zwo、webhook 实时同步、国际版、其它码表 provider。
- ⚠️ **派生指标公式严格按权威定义实现**,不要自己发挥。NP/IF/TSS/CTL/ATL/TSB 都有公认公式,且必须有单元测试验证(与 Strava/iGPSport 显示误差 < 2%)。
- ⚠️ **Compact format 是必需项不是优化项**:stream 输出永远是 `{channel: {unit, values: [...]}}` 的裸数组形式,**绝不**返回 `[{time, power}, ...]` 这种逐点对象。从第一行 stream 代码就遵守。

## 核心架构

```
LLM Client ──stdio(MCP)── igpsport-mcp ──HTTPS── iGPSport 私有 API
```

server 内部分层(自上而下):

1. **MCP Tool Layer**(`tools/`)——见下 8 个 tool。
2. **Analysis Layer**(`analysis/`)——派生指标服务端算好再返回。
3. **FIT Parser**(`fit/parser.py`)——`fitparse` 封装。
4. **Client**(`client/`)——登录 + token 缓存、活动列表、FIT 下载。
5. **Local Cache**(`storage/`,SQLite)——`~/.cache/igpsport-mcp/`。

**关键洞察**:拿到 FIT 文件后,所有 stream / 派生指标 / 圈数据全部本地解析,跟 iGPSport 服务器零交互。因此只需维护极少数核心 endpoint(登录、活动列表、FIT 下载)。这是抗 API 漂移的设计核心,不要为了"省事"去逆向更多详情/统计接口。

**数据流**:工具优先查 SQLite 缓存,miss 才打 API;FIT 文件本地永久缓存;同一活动的后续请求零 API 调用。

## 8 个 MCP Tool

`list_activities`、`get_activity_summary`(最高频,务必准且快)、`get_activity_streams`(强制降采样+通道选择)、`get_activity_laps`、`get_athlete_profile`、`get_athlete_stats`、`compare_activities`、`analyze_training_load`(CTL/ATL/TSB 趋势,杀手 query)。

设计原则:输入参数极简;输出始终 compact JSON;返回 array 的工具都要有 `limit`;stream 类都要支持降采样;时间字段统一 ISO 8601 带时区,不用 unix timestamp。

## 派生指标

- **NP**:`((rolling_30s_avg(power))^4 的均值)^0.25`,要求输入 1Hz——所有 stream 计算前必须先重采样到 1Hz 连续时间。
- **IF** = NP / FTP;**TSS** = `duration_s * NP * IF / (FTP * 3600) * 100`。
- **CTL/ATL/TSB**:`daily_tss.ewm(alpha=1/42)` / `alpha=1/7`,TSB = CTL − ATL。
- **无功率计兜底**:hrTSS = `(duration_s/3600) * (avg_hr/LTHR)^2 * 100`,输出须标注 "estimated from HR"。
- **HR zones**:Friel 模型基于 LTHR;**Power zones**:Coggan 7-zone 基于 FTP。

## 配置(env vars)

必填:`IGPSPORT_USERNAME`、`IGPSPORT_PASSWORD`。
可选:`IGPSPORT_FTP`(功率阈值,瓦)、`IGPSPORT_LTHR`(乳酸阈心率)、`IGPSPORT_CACHE_DIR`(默认 `~/.cache/igpsport-mcp`)、`IGPSPORT_LOG_LEVEL`。

缓存目录布局:`token.json`(token + expires_at)、`activities.db`(SQLite)、`fit/{ride_id}.fit`。

## 技术栈与命令

包管理用 **uv**;lint/format 用 **ruff**;测试 **pytest** + **pytest-httpx**(mock HTTP)。核心依赖:`mcp`、`httpx`、`fitparse`、`pandas`、`numpy`、`cryptography`。

```bash
uv sync                          # 安装依赖
uv run python -m igpsport_mcp    # 本地启动 MCP server(stdio)
ruff check .                     # lint(要求零警告)
ruff format .                    # format
uv run pytest                    # 跑全部测试
uv run pytest tests/test_power.py            # 单文件
uv run pytest tests/test_power.py::test_np   # 单条用例
uv run pytest --cov=igpsport_mcp             # 覆盖率(总体 ≥70%,analysis 层 ≥90%)
```

发布:`uvx igpsport-mcp` 一次性运行 / `uv tool install igpsport-mcp` 全局安装。

## 质量红线

- public function 全部有 type hints;`ruff check` 零警告。
- 不写"AI 味"过浓的废话注释。
- 错误处理:凭证错误报 "Login failed, check IGPSPORT_USERNAME/PASSWORD";网络错误重试 3 次指数退避;API 变更抛 `IGPSportAPIChangedError` 并提示去 GitHub issue;单条 FIT 解析失败不影响其他活动。
