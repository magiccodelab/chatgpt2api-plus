# 简约画图 API

为自动化轮询调用而设计的精简接口，和 OpenAI 兼容接口（`/v1/images/generations`）并存。

- **Base URL**：`http://localhost:3009`
- **鉴权**：`Authorization: Bearer <auth-key>`（即 `config.json` 里的 `auth-key`）
- **响应图片编码**：`b64_json`（纯 base64，不含 `data:` 前缀；浏览器直接显示需拼 `data:image/png;base64,<b64_json>`）

---

## 首次部署

```bash
git clone <your-repo-url> && cd chatgpt2api
cp config.example.json config.json     # 按需修改 auth-key
docker compose up -d                   # 本地构建并启动，默认 3009 端口
```

---

## POST `/api/v1/generate`

### 请求

```http
POST /api/v1/generate HTTP/1.1
Content-Type: application/json
Authorization: Bearer <auth-key>
```

| 字段     | 类型    | 必填 | 默认            | 说明                                                |
|--------|-------|----|---------------|---------------------------------------------------|
| prompt | str   | ✅  | -             | 画图提示词                                             |
| model  | str   | ❌  | `gpt-image-2` | 模型名，取值见 `GET /v1/models`                          |
| n      | int   | ❌  | `1`           | 生成数量，`1-4`                                        |
| stream | bool  | ❌  | `false`       | `true` 时走 SSE 流；**推荐长任务用 stream 避免反向代理超时** |

---

### 模式 A：非流式（`stream=false`）

适用：快速单张生成，不担心超时。

成功（HTTP 200）：
```json
{
  "success": true,
  "created": 1735000000,
  "model": "gpt-image-2",
  "count": 1,
  "images": [
    { "b64_json": "iVBORw0KGgoAAAANS..." }
  ]
}
```

失败（HTTP 4xx/5xx）：
```json
{
  "success": false,
  "error": { "code": "rate_limit", "message": "no available image quota" }
}
```

**curl 示例**：
```bash
curl -sS http://localhost:3009/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer chatgpt2api" \
  -d '{"prompt":"一只漂浮在太空的猫","n":1}'
```

---

### 模式 B：流式 SSE（`stream=true`，推荐）

HTTP 始终返回 200，状态通过事件推送。**服务端每 15 秒发送一次 `: heartbeat` 注释行**，保证反向代理/客户端长链接不被中断。

事件示例：
```
: stream-open

data: {"type":"start","model":"gpt-image-2","n":2}

data: {"type":"progress","index":1,"total":2}

data: {"type":"image","index":1,"b64_json":"iVBORw0KGgo..."}

: heartbeat

data: {"type":"image","index":2,"b64_json":"iVBORw0KGgo..."}

data: {"type":"done","count":2,"created":1735000000}

data: [DONE]
```

事件类型：

| type       | 字段                                | 说明                       |
|------------|-----------------------------------|--------------------------|
| `start`    | `model`, `n`                      | 任务开始                     |
| `progress` | `index`, `total`                  | 某张图生成中（进度提示，可忽略）         |
| `image`    | `index`, `b64_json`               | 某张图完成，`b64_json` 为 base64 |
| `done`     | `count`, `created`                | 全部完成                     |
| `error`    | `code`, `message`                 | 任务中途出错（见下方错误码）           |

**心跳注释行**：以 `:` 开头的行（SSE 规范，客户端应忽略），仅用于保活。

**curl 示例**：
```bash
curl -N -sS http://localhost:3009/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer chatgpt2api" \
  -d '{"prompt":"赛博朋克雨夜东京","n":2,"stream":true}'
```

---

## 错误码

统一格式：`{"success": false, "error": {"code": "...", "message": "..."}}`（流式下裹在 `{"type":"error", ...}` 事件里）

| HTTP | code              | 含义                 |
|------|-------------------|--------------------|
| 400  | `invalid_request` | 参数错误（如 prompt 为空） |
| 401  | `unauthorized`    | API key 缺失或错误      |
| 429  | `rate_limit`      | 号池无可用额度            |
| 502  | `upstream_error`  | 上游 ChatGPT 异常    |
| 502  | `empty_result`    | 上游未返回有效图片         |

---

## Python 客户端示例（流式）

```python
import json
import requests

url = "http://localhost:3009/api/v1/generate"
headers = {"Authorization": "Bearer chatgpt2api", "Content-Type": "application/json"}
body = {"prompt": "星空下的猫", "n": 1, "stream": True}

with requests.post(url, headers=headers, json=body, stream=True, timeout=None) as r:
    r.raise_for_status()
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or raw.startswith(":"):  # 空行或心跳
            continue
        if not raw.startswith("data: "):
            continue
        payload = raw[6:]
        if payload == "[DONE]":
            break
        event = json.loads(payload)
        if event.get("type") == "image":
            # event["b64_json"] 就是 base64 字符串
            # 浏览器展示拼前缀：f"data:image/png;base64,{event['b64_json']}"
            with open(f"out_{event['index']}.png", "wb") as f:
                import base64
                f.write(base64.b64decode(event["b64_json"]))
        elif event.get("type") == "error":
            print("ERR:", event)
            break
```

---

## 和 OpenAI 兼容接口的关系

| 对比项     | `/api/v1/generate`（本接口） | `/v1/images/generations`（OpenAI 兼容） |
|---------|------------------------|-------------------------------------|
| 用途      | 自动化/脚本调用               | 兼容 OpenAI SDK / Cherry Studio 等     |
| 字段      | 精简（4 个）                | 对齐 OpenAI，字段较多                    |
| 错误格式    | 统一 `success/error` 结构 | OpenAI 风格 `detail.error`             |
| 流心跳   | ✅ 每 15s             | ❌                                |
| 返回编码  | `b64_json`             | `b64_json`（同）                 |

两者可并存使用，底层共享号池与额度。
