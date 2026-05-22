# MCP Servers

为 AIOps 智能诊断和学术搜索提供日志查询、监控数据与 arXiv 检索工具。

## 📚 服务列表

### CLS Server (`cls_server.py`)
**日志查询服务** - 端口 8003

**核心工具：**
- `get_current_timestamp` - 获取当前时间戳
- `get_topic_info_by_name` - 查询日志主题
- `search_log` - 日志搜索
- `search_service_logs` - 服务日志查询（支持级别筛选）
- `analyze_log_pattern` - 日志模式分析

### Monitor Server (`monitor_server.py`)
**监控数据服务** - 端口 8004

**核心工具：**
- `query_cpu_metrics` - CPU 使用率查询
- `query_memory_metrics` - 内存使用查询
- `query_process_list` - 进程列表
- `search_historical_tickets` - 历史工单查询
- `get_service_info` / `list_all_services` - 服务信息

### arXiv MCP (`arxiv-mcp-server`)
**学术搜索服务** - stdio，由应用内 MCP Client 按需启动

**配置项：**
- `MCP_ARXIV_ENABLED` - 是否启用 arXiv MCP
- `MCP_ARXIV_COMMAND` - 默认 `uv`
- `MCP_ARXIV_ARGS` - 默认 `["tool","run","arxiv-mcp-server","--storage-path","arxiv-papers"]`

该服务参考 Go 版使用 `blazickjp/arxiv-mcp-server`，用于论文搜索、下载和本地论文缓存。

## 🚀 快速开始

### 安装依赖
```bash
pip install fastmcp
```

### 启动服务

**方式一：使用 Makefile（推荐）**
```bash
make mcp-start   # 启动所有 MCP 服务
make mcp-stop    # 停止所有 MCP 服务
make mcp-status  # 查看服务状态
```

**方式二：手动启动**
```bash
python mcp_servers/cls_server.py
python mcp_servers/monitor_server.py
```

arXiv MCP 不需要单独常驻启动；启用后会在 Agent 加载 MCP 工具时通过 stdio 自动拉起：

```bash
uv tool run arxiv-mcp-server --storage-path arxiv-papers
```

## 💡 使用示例

### AIOps 诊断场景

```
用户: data-sync-service 出现告警，请排查

Agent 自动执行:
1. list_all_services() → 查看所有服务状态
2. get_service_info("data-sync-service") → 获取服务详情
3. query_cpu_metrics("data-sync-service") → CPU 趋势分析
4. search_service_logs("data-sync-service", level="error") → 错误日志
5. analyze_log_pattern("data-sync-service") → 日志模式分析
6. search_historical_tickets(service_name="data-sync-service") → 历史工单
7. 综合分析 → 生成诊断报告和修复建议
```

### 学术搜索场景

```
用户: 检索近期 arXiv 上与多智能体运维相关的论文，并总结关键思路

Agent 自动执行:
1. 通过 arXiv MCP 搜索相关论文
2. 读取论文元信息/摘要
3. 汇总研究方向、关键方法和可参考工作
```

### 工具参数示例

**查询 CPU 指标：**
```python
query_cpu_metrics(
    service_name="data-sync-service",
    start_time="2024-02-14 02:00:00",
    interval="1m"
)
```

**搜索错误日志：**
```python
search_service_logs(
    service_name="data-sync-service",
    log_level="error",
    keyword="timeout",
    limit=100
)
```

**搜索历史工单：**
```python
search_historical_tickets(
    service_name="data-sync-service",
    issue_type="cpu",
    limit=10
)
```

## 🔧 高级配置

### 接入真实 API

当前返回模拟数据。接入真实 API 步骤：

**腾讯云 CLS：**
```bash
# 安装 SDK
pip install tencentcloud-sdk-python

# 配置环境变量
export TENCENTCLOUD_SECRET_ID="your-id"
export TENCENTCLOUD_SECRET_KEY="your-key"

# 在 cls_server.py 中集成
from tencentcloud.cls.v20201016 import cls_client
```

**其他监控系统：**
- Prometheus
- Grafana
- 云监控（腾讯云/阿里云/AWS）
- 自建监控平台

### 自定义 Mock 数据

修改各 Server 文件中的数据生成逻辑，模拟实际场景。

## 📚 参考资料

- [FastMCP 文档](https://github.com/jlowin/fastmcp)
- [MCP 协议](https://modelcontextprotocol.io/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [主项目 README](../README.md)

---

**注意**: 当前版本返回模拟数据，生产环境需配置真实 API。
