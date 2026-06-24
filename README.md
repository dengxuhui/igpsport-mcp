# igpsport-mcp

把 **iGPSport 骑行数据**接入 Claude 等 LLM 客户端的本地 [MCP](https://modelcontextprotocol.io) server。用自然语言分析你的训练:_"我这周训练负荷怎么样?"_ _"对比一下上周和这周的两次长距离骑行。"_ _"我收藏的爬坡赛段排名怎样?"_ _"今年骑了多少公里,有哪些个人最佳?"_

**差异化**:NP / IF / TSS / CTL / ATL / TSB 这些派生训练指标在 **MCP 层算好**再返回——LLM 拿到的是可直接讲故事的数字,而不是一堆原始 stream。

```
你:  我最近 90 天的训练负荷趋势?是不是该减量了?
Claude(经由 analyze_training_load):
     当前 CTL(体能)72,ATL(疲劳)91,TSB(状态)-19 —— 处于明显疲劳累积区。
     过去两周 TSS 持续高于 CTL,建议安排 3-5 天恢复周让 TSB 回到 -5 以上……
```

> ⚠️ **非官方项目**。本工具通过**逆向 iGPSport 私有网页 API** 工作,iGPSport 随时可能改接口导致失效;请自行评估账号风险,**风险自负**。纯本地 stdio 运行,**你的数据不经任何第三方服务器**。

## 安装

需要 Python ≥ 3.11 和 [uv](https://docs.astral.sh/uv/)。

```bash
uvx igpsport-mcp            # 一次性运行(MCP 客户端会自动拉起)
uv tool install igpsport-mcp   # 或全局安装
```

## 配置(环境变量)

| 变量 | 必填 | 说明 |
|---|---|---|
| `IGPSPORT_USERNAME` | ✅ | iGPSport 账号(手机号) |
| `IGPSPORT_PASSWORD` | ✅ | 密码 |
| `IGPSPORT_FTP` | 选填 | 功率阈值(瓦)。**不填会自动读取 iGPSport 账号里设置的 FTP**;填了则覆盖 |
| `IGPSPORT_LTHR` | 选填 | 乳酸阈心率(bpm),用于心率区间与 hrTSS 兜底。**不填同样自动从 iGPSport 读取**;填了则覆盖 |
| `IGPSPORT_CACHE_DIR` | 选填 | 缓存目录,默认 `~/.cache/igpsport-mcp` |
| `IGPSPORT_LOG_LEVEL` | 选填 | 默认 `INFO` |

> FTP / LTHR 现在默认从你 iGPSport 账号的运动信息里自动读取(还会带出体重、最大心率),所以**通常无需手动填**。只有当你想用与 App 不同的阈值时,才设这两个环境变量来覆盖。若账号里也没设 FTP,则无法计算 IF / TSS / CTL / ATL / TSB —— 请到 iGPSport 里补上,或填 `IGPSPORT_FTP`。

## 接入 Claude

### Claude Desktop

把下面这段拷进 `claude_desktop_config.json`(macOS:`~/Library/Application Support/Claude/`),填好凭证后**完全退出并重开** Claude Desktop:

```json
{
  "mcpServers": {
    "igpsport": {
      "command": "uvx",
      "args": ["igpsport-mcp"],
      "env": {
        "IGPSPORT_USERNAME": "你的手机号",
        "IGPSPORT_PASSWORD": "你的密码"
      }
    }
  }
}
```

> FTP / LTHR 默认自动从 iGPSport 账号读取,无需填写。只有想覆盖 App 里的阈值时,才在 `env` 里加 `"IGPSPORT_FTP": "250"`、`"IGPSPORT_LTHR": "160"`。

### Claude Code

```bash
claude mcp add igpsport --scope user \
  --env IGPSPORT_USERNAME=你的手机号 \
  --env IGPSPORT_PASSWORD=你的密码 \
  -- uvx igpsport-mcp
```

> 同样,需要覆盖阈值时再追加 `--env IGPSPORT_FTP=250 --env IGPSPORT_LTHR=160`。

加完用 `/mcp` 或 `claude mcp list` 确认状态为 connected。

> **连不上 / 找不到命令?** 多半是 `uvx` 不在客户端的 PATH 里(尤其 Claude Desktop 常取不到登录 shell 的 PATH)。把配置里的 `"uvx"` / `command` 换成 `which uvx` 输出的**绝对路径**(如 `/Users/你/.local/bin/uvx`)即可。

## 提供的 12 个工具

**活动与训练(8)**

| 工具 | 用途 |
|---|---|
| `list_activities` | 列出活动(支持日期范围、分页) |
| `get_activity_summary` | 单次活动派生指标(NP/IF/TSS/work、心率与功率区间停留时间) |
| `get_activity_streams` | 时间序列(强制降采样 + 通道选择,token 友好) |
| `get_activity_laps` | 圈/分段数据(逐圈 NP) |
| `get_athlete_profile` | 训练参数:FTP/LTHR(自动读 iGPSport 或用环境变量覆盖);体重、最大心率始终从 iGPSport 读取;含区间边界 |
| `get_athlete_stats` | 周期聚合统计(本地从活动列表算) |
| `compare_activities` | 多次活动对比(2–5 条) |
| `analyze_training_load` | CTL/ATL/TSB 趋势 + 状态解读(杀手 query) |

**赛段(3)**

| 工具 | 用途 |
|---|---|
| `list_segments_collected` | 我收藏(收星)的赛段列表,含我的最好成绩 |
| `get_segment_detail` | 赛段详情:距离/坡度/爬升 + KOM + 最快榜 + 我的 PR |
| `get_segment_rank` | 赛段排行榜(`query_type` 1=总榜、2=年度等),含我的排名 |

**统计与成就(1)**

| 工具 | 用途 |
|---|---|
| `get_member_statistics` | 官方年度统计与个人最佳:总里程/时长/卡路里/TSS、逐月里程、距离里程碑、各项 PR(最远/最久/最快/最大功率/最大爬升) |

## 派生指标说明

- **NP**(标准化功率):`((30s 滑动均值)^4 的均值)^0.25`,计算前 stream 重采样到 1Hz。
- **IF** = NP / FTP;**TSS** = `时长 × NP × IF / (FTP × 3600) × 100`。
- **CTL / ATL / TSB**:日 TSS 的指数加权(α=1/42、1/7),TSB = CTL − ATL。
- **无功率计兜底**:hrTSS = `(时长/3600) × (平均心率/LTHR)² × 100`,会标注 `estimated from HR`。
- **区间模型**:心率用 Friel(基于 LTHR),功率用 Coggan 7 区(基于 FTP)。

## FAQ

**Q:必须有功率计吗?**
A:不必。没功率计时心率相关指标照常,TSS 走 hrTSS 兜底(精度较低,会标注)。但建议填 FTP 以解锁功率指标。

**Q:数据会上传到哪里吗?**
A:不会。除了向 iGPSport 拉你自己的数据,一切都在本地;FIT 文件与派生指标缓存在本地。

**Q:接口失效了怎么办?**
A:iGPSport 改版可能导致失效,工具会抛出明确错误。欢迎到 [Issues](https://github.com/dengxuhui/igpsport-mcp/issues) 反馈。

**Q:支持跑步/其它码表吗?**
A:不支持。本项目专注 iGPSport 骑行数据。

## 开发

```bash
uv sync --extra dev
uv run pytest            # 测试
uv run pytest -m integration   # 联网集成测试
ruff check . && ruff format .  # lint/format
```

## License

[MIT](LICENSE)。本项目与 iGPSport 官方无任何关联。
