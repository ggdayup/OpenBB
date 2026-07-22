import os
import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from openbb_ai.helpers import message_chunk
import httpx
import uvicorn

app = FastAPI(title="OpenBB Copilot Native Agent Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LITELLM_API_URL = os.getenv("LITELLM_API_URL", "http://host.docker.internal:32000/v1/chat/completions")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-1234")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-3.6-flash")

@app.get("/agents.json")
@app.get("/agents.json/agents.json")
def get_agent_manifest(request: Request):
    host_header = request.headers.get("host", "100.90.139.116:32001")
    base_url = f"http://{host_header}"
    return {
        "litellm-gemini-copilot": {
            "name": "LiteLLM Gemini Copilot",
            "description": "Official OpenBB Copilot powered by LiteLLM & Gemini 3.6 Flash",
            "image": "https://openbb.co/favicon.ico",
            "endpoints": {
                "query": f"{base_url}/query"
            },
            "features": {
                "streaming": True,
                "widgets": True,
                "widget-dashboard-select": True,
                "widget-dashboard-search": True
            }
        }
    }

@app.post("/query")
async def query_agent(request: Request):
    raw_body = await request.json()
    print(f"[OPENBB QUERY INCOMING]: {json.dumps(raw_body, ensure_ascii=False)[:500]}")

    raw_messages = raw_body.get("messages", [])
    clean_messages = [
        {"role": "system", "content": "You are a professional financial AI assistant for OpenBB Workspace. Analyze user queries and active widget context carefully."}
    ]

    ROLE_MAP = {
        "human": "user",
        "user": "user",
        "ai": "assistant",
        "assistant": "assistant",
        "system": "system"
    }

    for m in raw_messages:
        raw_role = str(m.get("role", "user")).lower()
        role = ROLE_MAP.get(raw_role, "user")
        content = m.get("content", "")

        # 兼容 OpenBB 富文本/块级消息解析
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    elif "text" in item:
                        texts.append(str(item["text"]))
                    else:
                        texts.append(json.dumps(item, ensure_ascii=False))
            content = "\n".join(texts)
        elif isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        elif not isinstance(content, str):
            content = str(content)

        clean_messages.append({"role": role, "content": content})

    # 提取选中的 widget / context 信息
    widgets_info = raw_body.get("widgets") or raw_body.get("context") or raw_body.get("workspace_state")
    if widgets_info and len(clean_messages) > 1:
        widget_str = f"\n\n[Active Dashboard Context & Widgets]:\n{json.dumps(widgets_info, ensure_ascii=False, indent=2)}"
        clean_messages[-1]["content"] += widget_str

    litellm_payload = {
        "model": DEFAULT_MODEL,
        "messages": clean_messages,
        "stream": True
    }

    async def stream_generator():
        headers = {
            "Authorization": f"Bearer {LITELLM_API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", LITELLM_API_URL, json=litellm_payload, headers=headers) as response:
                    if response.status_code != 200:
                        err_bytes = await response.aread()
                        err_msg = f"[LiteLLM Error {response.status_code}]: {err_bytes.decode('utf-8', errors='ignore')}"
                        print(err_msg)
                        mc = message_chunk(err_msg)
                        yield {
                            "event": mc.event,
                            "data": mc.data if isinstance(mc.data, str) else mc.data.model_dump_json()
                        }
                        return

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                delta = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    mc = message_chunk(delta)
                                    yield {
                                        "event": mc.event,
                                        "data": mc.data if isinstance(mc.data, str) else mc.data.model_dump_json()
                                    }
                            except json.JSONDecodeError:
                                continue
        except Exception as ex:
            print(f"[BRIDGE EXCEPTION]: {str(ex)}")
            mc = message_chunk(f"[Bridge Error]: {str(ex)}")
            yield {
                "event": mc.event,
                "data": mc.data if isinstance(mc.data, str) else mc.data.model_dump_json()
            }

    return EventSourceResponse(stream_generator())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=32001)
