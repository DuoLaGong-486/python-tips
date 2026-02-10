# SSE Streaming Example

本项目演示如何使用 Python 的 `requests` 库接收 Server-Sent Events (SSE) 流式响应。

## 什么是 SSE?

Server-Sent Events (SSE) 是一种 Web 技术，允许服务器主动向客户端推送数据。与 WebSocket 不同，SSE 是单向的（服务器到客户端），基于 HTTP 协议，使用简单，天然支持断线重连。

## 项目结构

```
sse_streaming_example/
├── server.py          # SSE 服务器端 (FastAPI)
├── client.py          # SSE 客户端 (requests)
├── requirements.txt   # 项目依赖
└── README.md          # 本文档
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务器

```bash
python server.py
```

服务器将在 `http://127.0.0.1:8000` 启动。

### 3. 运行客户端

在另一个终端中运行客户端示例：

```bash
python client.py
```

## 可用的 SSE 端点

| 端点 | 描述 | 更新频率 |
|------|------|----------|
| `/stream/time` | 时间流 | 每秒 |
| `/stream/stocks` | 股票数据流 | 每500ms |
| `/stream/progress/{task_id}` | 任务进度流 | 模拟处理时间 |
| `/stream/chat` | 聊天消息流 | 随机间隔 |
| `/stream/heartbeat` | 心跳流 | 每5秒 |

## SSE 数据格式

SSE 使用纯文本格式，每条消息以双换行符结束：

```
event: <事件类型>
id: <事件ID>
retry: <重连时间(毫秒)>
data: <JSON数据或文本>

```

### 示例

```javascript
// 服务器发送
event: stock_update
id: stock-123
data: {"symbol": "AAPL", "price": 175.50, "change": 2.3}

```

## 客户端使用示例

### 基础用法

```python
import requests

url = "http://127.0.0.1:8000/stream/time"

with requests.get(url, stream=True) as response:
    for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
        print(chunk)
```

### 使用 SSEClient 类

```python
from client import SSEClient, SSEEvent

def handle_event(event: SSEEvent):
    print(f"事件类型: {event.event}")
    print(f"数据: {event.data}")

client = SSEClient(
    url="http://127.0.0.1:8000/stream/stocks",
    event_handler=handle_event,
    max_retry=3
)

client.start()
# 客户端会自动在后台运行
import time
time.sleep(10)
client.stop()
```

### 直接解析 SSE 数据

```python
import requests
import json

def parse_sse_line(line):
    """解析单行 SSE 数据"""
    if ": " in line:
        field, value = line.split(": ", 1)
        return field.lower(), value
    return None, None

url = "http://127.0.0.1:8000/stream/stocks"

session = requests.Session()
session.headers.update({
    "Accept": "text/event-stream",
    "Cache-Control": "no-cache"
})

response = session.get(url, stream=True)

buffer = ""
for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
    buffer += chunk
    
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        
        if not line.strip():  # 空行表示事件结束
            # 处理完整事件
            buffer = ""
            continue
        
        field, value = parse_sse_line(line)
        if field == "data":
            data = json.loads(value)
            print(f"收到数据: {data}")
```

## 核心功能

### 1. SSEClient 类

| 方法 | 描述 |
|------|------|
| `start(blocking=True)` | 启动客户端 |
| `stop()` | 停止客户端 |
| `is_connected` | 检查连接状态 |
| `event_counts` | 获取事件统计 |

### 2. SSEEvent 数据类

| 属性 | 描述 |
|------|------|
| `event` | 事件类型 |
| `data` | 事件数据 (dict 或 str) |
| `id` | 事件 ID |
| `retry` | 重连时间 |

## 最佳实践

### 1. 设置合适的超时时间

```python
client = SSEClient(
    url=url,
    timeout=60.0  # 60秒超时
)
```

### 2. 实现重连机制

```python
client = SSEClient(
    url=url,
    max_retry=5,       # 最多重试5次
    retry_delay=2.0    # 每次重试间隔2秒
)
```

### 3. 处理连接断开

```python
def on_disconnected():
    print("连接已断开，准备重连...")

client = SSEClient(
    url=url,
    connection_error_handler=on_disconnected
)
```

### 4. 使用心跳保持连接

```python
def handle_heartbeat(event):
    print(f"心跳: {event.data}")

client = SSEClient(
    url="http://127.0.0.1:8000/stream/heartbeat",
    event_handler=handle_heartbeat
)
```

## 应用场景

1. **实时通知** - 推送系统消息、警报
2. **进度更新** - 文件上传、数据处理进度
3. **实时数据** - 股票行情、物联网传感器数据
4. **日志流** - 实时日志收集和监控

## 注意事项

1. SSE 是单向通信，如果需要双向通信，请使用 WebSocket
2. SSE 天然支持自动重连，但建议在客户端实现额外的重试逻辑
3. 大多数浏览器限制同域 SSE 连接数，注意连接管理
4. 在代理服务器后面时，确保正确配置 `Cache-Control: no-cache` 头

## 清理资源

```python
client = SSEClient(url=url)
client.start()

# 使用完毕后记得停止
client.stop()
```

## 测试所有端点

```bash
# 启动服务器
python server.py

# 在另一个终端运行所有示例
python client.py
# 然后选择 'a' 运行所有示例
```

## License

MIT
