# OpenBB 自部署全免费 (Self-Hosted 100% Free) 产品需求文档 (PRD)

## 1. 项目背景与目标 (Background & Goals)
打造一个完全自主可控、本地部署且运维成本为零（零服务订阅费、零付费 API 依赖）的 OpenBB 资产分析与金融数据终端环境，并为 AI Agent (如 Claude Code, Hermes) 提供开箱即用的 MCP 工具链接入能力。

- **核心原则**：自部署、零订阅费、全开源码、私密安全、AI 原生接入。
- **目标用户**：个人量化研究员、金融分析师、AI Agent 开发者及独立开发者。

---

## 2. 核心架构与模块规范 (Architecture & Components)

### 2.1 数据层（全免费数据源）
仅集成与启用无需付费或提供免费额度/免密钥的数据提供商 (Data Providers)：
- **股票/行情**: `yfinance`, `sec` (SEC EDGAR 申报文件), `cboe`, `finviz`, `wsj`
- **宏观经济/央行**: `fred` (美联储经济数据), `federal_reserve`, `ecb` (欧洲央行), `imf`, `oecd`, `bls`
- **监管/政务/期货**: `cftc` (持仓报告), `congress_gov`, `government_us`
- **学术与基本面**: `famafrench`, `econdb`, `multpl`

### 2.2 服务与部署层
- **环境隔离与持久化**: 提供干净的 Python 独立虚拟环境 (`.venv`) 与 Docker 容器化编排方案，配合磁盘缓存与密钥挂载。
- **服务暴露**: 
  - **REST API 端点**: 部署 OpenBB Platform FastAPI 后端服务（默认监听端口 `6900`，提供 OpenAPI 文档）。
  - **MCP Agent 节点**: 集成 `openbb-mcp-server` 扩展服务（默认监听端口 `8001`），支持标准 `streamable-http` 与 `stdio` 传输模式。
- **高可用与开机自启**: 使用 Docker Compose `restart: always` 策略，实现随 Docker 引擎与宿主机重启全自动无感拉起。
- **安全与远程接入**: 全局绑定网络网卡 (`0.0.0.0`)，结合 **Tailscale 私网网卡**（本机 IP: `100.90.139.116`），实现免公网 IP、免端口租赁的跨设备加密访问。

### 2.3 交互与 AI Agent 工具层
- **OpenBB Platform SDK / CLI**: 本地 Python SDK (`openbb`) 与命令行快速检索界面。
- **AI Agent 工具接口**: 
  - **Claude Code / Claude Desktop 原生接入**: 支持在 `mcp.json` 中挂载 `http://127.0.0.1:8001/mcp` 或 `stdio` 命令。
  - **Hermes / 远程 Agent 接入**: 支持通过 Tailscale `http://100.90.139.116:8001` 进行远程 MCP 工具调用。
  - **Python Function Calling**: 提供 `ggdayup/ai_agent_adapter.py` 适配层。

---

## 3. 需求功能清单 (Feature Scope)

| 模块 | 功能描述 | 选用提供者/工具 | 成本 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| **基础环境** | Docker 一键启动与依赖自动构建 (无资源硬限制) | Docker / Docker Compose | ￥0 | ✅ 已实现 |
| **美股行情与指标** | 股票历史 K 线、技术指标计算与多源降级 | `yfinance`, `finviz`, `cboe` | ￥0 | ✅ 已实现 |
| **财报与监管** | SEC EDGAR 10-K/10-Q 检索与解析 | `sec` | ￥0 | ✅ 已实现 |
| **宏观经济** | 利率、通胀、GDP、失业率等宏观指标 | `fred`, `federal_reserve`, `ecb` | ￥0 | ✅ 已实现 |
| **API 服务化** | 本地 REST API 服务及 OpenAPI 文档 | OpenBB FastAPI (端口 6900) | ￥0 | ✅ 已实现 |
| **MCP Agent 接口** | 为 Claude Code / Hermes 提供 MCP 自动化服务 | OpenBB MCP Server (端口 8001) | ￥0 | ✅ 已实现 |
| **远程加密访问** | 跨设备（手机/笔记本）Tailscale 局域网访问 | Tailscale (`100.90.139.116`) | ￥0 | ✅ 已实现 |
| **开机自启** | 随系统/Docker 自动唤醒服务 | Compose `restart: always` | ￥0 | ✅ 已实现 |

---

## 4. 非功能性需求 (Non-Functional Requirements)
- **性能与缓存防护**: 开启磁盘/SQLite 本地缓存 (`~/OpenBBUserData/cache`)，缩短响应时间 (< 200ms) 并防御免费 API 频控 (Rate Limit)。
- **高可用与自动重试**: 配置 `user_settings.json` Provider 降级队列 (`yfinance -> cboe -> finviz`)，主源异常自动切备源。
- **开箱即用**: 提供 `ggdayup/` 目录下的一键部署脚本 (`start_free_openbb.sh`) 与自动化测试校验 (`verify_free_providers.py`)。

---

## 5. 扩展规划（暂缓实施 / Deferred Extensions）

### 5.1 Interactive Brokers (IBKR) 账户与数据对接
- **集成目标**：支持接入个人 IBKR 账户（通过 TWS API / IB Gateway / `ib_insync` 库），实现账户持仓查询、实时深度盘口拉取与自动化交易接口扩展。
- **成本控制**：IBKR 账户的 API 本身免费使用，不增加额外外部服务费用。
- **实施状态**：**[暂缓实施 - On Hold]**。首期优先完成全免费公共数据源与基础自部署环境构建，待基础平台稳定后再开展 IBKR 通道接入。