import os
import json
import re
import uuid
import time
import httpx
import uvicorn
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from openbb_ai.models import (
    QueryRequest,
    LlmClientMessage,
    LlmClientFunctionCallResultMessage,
    WidgetCollection,
    FunctionCallSSE,
    FunctionCallSSEData,
    RoleEnum,
)
from openbb_ai.helpers import (
    message_chunk,
    reasoning_step,
    prompt_suggestions,
    table,
    chart,
    cite,
    citations,
)

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
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemma-4-26b-a4b-it")

# Cache for dynamic models list
_MODELS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "options": []}
CACHE_TTL = 60.0  # 60 seconds TTL

def format_model_label(model_id: str) -> str:
    if model_id.startswith("openrouter/"):
        clean_name = model_id[len("openrouter/"):]
        is_free = ":free" in clean_name
        clean_name = clean_name.replace(":free", "")
        if "/" in clean_name:
            provider, name = clean_name.split("/", 1)
            name = name.replace("-", " ").replace("_", " ").title()
            tag = f"[OpenRouter/{provider.title()}]"
        else:
            name = clean_name.replace("-", " ").replace("_", " ").title()
            tag = "[OpenRouter]"
        if is_free:
            name += " (Free)"
        return f"{tag} {name}"
    elif "gemini" in model_id.lower() or "gemma" in model_id.lower():
        clean_id = model_id.replace("gemini/", "").replace("models/", "")
        clean_name = clean_id.replace("-", " ").replace("_", " ").title()
        return f"[Google Native] {clean_name}"
    elif model_id.startswith("gpt-") or "openai/" in model_id:
        clean_name = model_id.replace("openai/", "").upper()
        return f"[OpenAI] {clean_name}"
    else:
        return f"[LiteLLM] {model_id}"

async def fetch_available_models() -> List[Dict[str, str]]:
    now = time.time()
    if _MODELS_CACHE["options"] and (now - _MODELS_CACHE["timestamp"]) < CACHE_TTL:
        return _MODELS_CACHE["options"]

    models_url = LITELLM_API_URL.replace("/chat/completions", "/models")
    headers = {"Authorization": f"Bearer {LITELLM_API_KEY}"}

    fallback_options = [
        {"label": "[Google Native] Gemma 4 26B", "value": "gemma-4-26b-a4b-it"},
        {"label": "[Google Native] Gemini 3.6 Flash", "value": "gemini-3.6-flash"},
        {"label": "[Google Native] Gemini 3.5 Flash Lite", "value": "gemini-3.5-flash-lite"}
    ]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code == 200:
                raw_data = resp.json().get("data", [])
                options = []
                seen_ids = set()

                for item in raw_data:
                    m_id = item.get("id", "")
                    if not m_id or m_id.startswith("models/"):
                        continue
                    if m_id.startswith("gemini/"):
                        short_id = m_id[len("gemini/"):]
                        if short_id in seen_ids:
                            continue
                    elif f"gemini/{m_id}" in seen_ids:
                        seen_ids.remove(f"gemini/{m_id}")
                        options = [o for o in options if o["value"] != f"gemini/{m_id}"]

                    if m_id in seen_ids:
                        continue

                    seen_ids.add(m_id)
                    options.append({
                        "label": format_model_label(m_id),
                        "value": m_id
                    })

                if options:
                    _MODELS_CACHE["options"] = options
                    _MODELS_CACHE["timestamp"] = now
                    return options

    except Exception as e:
        print(f"[WARN]: Failed to fetch models from LiteLLM: {e}")

    _MODELS_CACHE["options"] = fallback_options
    _MODELS_CACHE["timestamp"] = now
    return fallback_options

# Pass 1 Tools (includes get_widget_data for data retrieval)
AGENT_TOOLS_PASS1 = [
    {
        "type": "function",
        "function": {
            "name": "get_widget_data",
            "description": "Request raw underlying data from specific widgets currently displayed on the user's dashboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "widget_uuid": {"type": "string", "description": "UUID of the target dashboard widget"},
                                "origin": {"type": "string", "description": "Origin of the widget (e.g. 'openbb')"},
                                "id": {"type": "string", "description": "Widget endpoint ID (e.g. 'equity_historical')"},
                                "input_args": {"type": "object", "description": "Input parameters for widget data execution"}
                            },
                            "required": ["widget_uuid", "origin", "id"]
                        }
                    }
                },
                "required": ["data_sources"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_table_artifact",
            "description": "Render structured tabular data as an interactive OpenBB table artifact in the user workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Title of the table artifact"},
                    "description": {"type": "string", "description": "Description of table data"},
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of dictionary records representing rows"
                    }
                },
                "required": ["data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_chart_artifact",
            "description": "Render a visual chart artifact (line, bar, scatter, pie, donut) in the OpenBB user workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["line", "bar", "scatter", "pie", "donut"]},
                    "name": {"type": "string", "description": "Chart title"},
                    "description": {"type": "string", "description": "Chart description"},
                    "data": {"type": "array", "items": {"type": "object"}},
                    "x_key": {"type": "string", "description": "X-axis variable key for line/bar/scatter"},
                    "y_keys": {"type": "array", "items": {"type": "string"}, "description": "Y-axis variable key(s)"},
                    "angle_key": {"type": "string", "description": "Angle variable key for pie/donut"},
                    "callout_label_key": {"type": "string", "description": "Label variable key for pie/donut"}
                },
                "required": ["type", "data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "prompt_suggestions",
            "description": "Send 2 to 4 recommended follow-up prompt suggestions to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of recommended follow-up questions"
                    }
                },
                "required": ["suggestions"]
            }
        }
    }
]

# Pass 2 Tools (omits get_widget_data so model does not loop re-requesting already fetched data)
AGENT_TOOLS_PASS2 = [t for t in AGENT_TOOLS_PASS1 if t["function"]["name"] != "get_widget_data"]

@app.get("/agents.json")
@app.get("/agents.json/agents.json")
async def get_agent_manifest(request: Request):
    host_header = request.headers.get("host", "100.90.139.116:32001")
    base_url = f"http://{host_header}"
    model_options = await fetch_available_models()

    return {
        "litellm-gemini-copilot": {
            "name": "LiteLLM Gemini Copilot",
            "description": "Official OpenBB Copilot with Dynamic LiteLLM Model Selector",
            "image": "https://openbb.co/favicon.ico",
            "endpoints": {
                "query": f"{base_url}/query"
            },
            "features": {
                "streaming": True,
                "widgets": True,
                "widget-dashboard-select": True,
                "widget-dashboard-search": True,
                "prompt-suggestions": True,
                "agent-tools": True,
                "citations": True,
                "select-model": {
                    "label": "Model",
                    "type": "select",
                    "default": DEFAULT_MODEL,
                    "description": "Choose active LiteLLM backend model & provider",
                    "options": model_options
                }
            }
        }
    }

def format_widgets_summary(widgets_collection: Optional[WidgetCollection]) -> str:
    if not widgets_collection:
        return ""
    all_widgets = widgets_collection.primary + widgets_collection.secondary + widgets_collection.extra
    if not all_widgets:
        return ""
    
    lines = ["\n[Available Dashboard Widgets Context]:"]
    for w in all_widgets:
        w_uuid = str(w.uuid)
        params_info = []
        for p in w.params:
            curr = getattr(p, "current_value", None)
            if curr is None:
                curr = getattr(p, "executed_value", None)
            if curr is None:
                curr = getattr(p, "default_value", None)
            params_info.append(f"{p.name}={curr}")
        param_str = ", ".join(params_info)
        lines.append(
            f"- Widget: '{w.name}' | UUID: '{w_uuid}' | Origin: '{w.origin}' | ID: '{w.widget_id}' | Params: [{param_str}] | Description: '{w.description}'"
        )
    lines.append(
        "\nINSTRUCTION FOR WIDGET DATA: If answering the user's query requires fetching content from any of the above widgets, YOU MUST invoke the 'get_widget_data' tool with the exact widget_uuid, origin, id, and input_args."
    )
    return "\n".join(lines)

def parse_tool_args(raw_args: str) -> Dict[str, Any]:
    if not raw_args:
        return {}
    cleaned = raw_args.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end+1])
            except Exception:
                pass
        return {}

def build_openai_messages(query_req: QueryRequest, has_tool_results: bool) -> List[Dict[str, Any]]:
    system_prompt = (
        "You are an expert financial AI assistant operating inside OpenBB Workspace (OpenBB Copilot protocol).\n"
        "You have access to tools for retrieving widget data, creating interactive table/chart artifacts, and offering prompt suggestions.\n\n"
        "Operational Rules:\n"
        "1. If the user asks about dashboard widgets, figures, or stock data available in dashboard widgets, call `get_widget_data` immediately.\n"
        "2. Present financial summaries clearly and in Markdown with structured tables and bullet points.\n"
        "3. When rendering interactive widgets, use `create_table_artifact` or `create_chart_artifact`.\n"
        "4. Conclude your final answer with `prompt_suggestions` offering 2-4 relevant follow-up questions."
    )

    if has_tool_results:
        system_prompt += (
            "\n\n[CRITICAL PASS 2 INSTRUCTION]: Widget data HAS ALREADY BEEN FETCHED and is provided in the tool messages below. "
            "DO NOT attempt to call `get_widget_data` again. Synthesize and analyze the provided data now, "
            "and stream out your complete financial analysis and markdown tables directly."
        )

    clean_messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    widget_str = format_widgets_summary(query_req.widgets)

    for idx, msg in enumerate(query_req.messages):
        if isinstance(msg, LlmClientFunctionCallResultMessage) or (isinstance(msg, dict) and msg.get("role") == "tool"):
            func_name = getattr(msg, "function", "get_widget_data")
            raw_data = getattr(msg, "data", [])
            data_content = []
            if isinstance(raw_data, list):
                for item in raw_data:
                    if hasattr(item, "model_dump"):
                        data_content.append(item.model_dump(exclude_none=True))
                    elif isinstance(item, dict):
                        data_content.append(item)
                    else:
                        data_content.append(str(item))
            else:
                data_content = str(raw_data)

            tool_call_id = f"call_{func_name}_{idx}"
            
            if clean_messages and clean_messages[-1]["role"] != "assistant":
                clean_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "arguments": json.dumps(getattr(msg, "input_arguments", {}), ensure_ascii=False)
                        }
                    }]
                })
            
            clean_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(data_content, ensure_ascii=False)
            })

        else:
            role_val = getattr(msg, "role", "user")
            if isinstance(role_val, RoleEnum):
                role_val = role_val.value
            role_str = str(role_val).lower()
            role = "user" if role_str in ["human", "user"] else ("assistant" if role_str in ["ai", "assistant"] else "system")

            raw_content = getattr(msg, "content", "")
            content_str = ""
            if isinstance(raw_content, str):
                content_str = raw_content
            elif isinstance(raw_content, list):
                texts = []
                for item in raw_content:
                    if isinstance(item, str):
                        texts.append(item)
                    elif isinstance(item, dict):
                        texts.append(item.get("text", json.dumps(item, ensure_ascii=False)))
                content_str = "\n".join(texts)
            elif isinstance(raw_content, dict):
                content_str = json.dumps(raw_content, ensure_ascii=False)
            else:
                content_str = str(raw_content)

            if idx == len(query_req.messages) - 1 and role == "user" and widget_str and not has_tool_results:
                content_str += widget_str

            clean_messages.append({"role": role, "content": content_str})

    if has_tool_results and clean_messages and clean_messages[-1]["role"] == "user":
        clean_messages[-1]["content"] += "\n\n[SYSTEM]: The requested widget data has been retrieved and is provided above. Proceed to stream your complete analysis."

    return clean_messages

def sanitize_openai_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not messages:
        return [{"role": "user", "content": "Hello"}]

    sanitized: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        tool_calls = m.get("tool_calls")

        if role == "assistant" and (content is None or str(content).strip() == "") and not tool_calls:
            continue

        if role == "user" and (content is None or str(content).strip() == ""):
            continue

        if sanitized and sanitized[-1].get("role") == role and role in ["user", "assistant"] and not tool_calls and not sanitized[-1].get("tool_calls"):
            existing_content = sanitized[-1].get("content") or ""
            new_content = content or ""
            sanitized[-1]["content"] = f"{existing_content}\n{new_content}".strip()
        else:
            sanitized.append(m)

    if not sanitized:
        sanitized = [{"role": "user", "content": "Hello"}]

    while sanitized and sanitized[-1].get("role") == "assistant":
        last_m = sanitized[-1]
        if not last_m.get("content") and not last_m.get("tool_calls"):
            sanitized.pop()
        else:
            sanitized.append({"role": "user", "content": "Please proceed with your financial analysis based on the retrieved data."})
            break

    return sanitized

@app.post("/query")
async def query_agent(request: Request):
    try:
        raw_body = await request.json()
    except Exception as e:
        print(f"[ERROR]: Invalid JSON request body: {e}")
        raw_body = {}

    print(f"[OPENBB QUERY INCOMING]: {json.dumps(raw_body, ensure_ascii=False)[:500]}")

    if isinstance(raw_body, dict) and "messages" in raw_body and isinstance(raw_body["messages"], list):
        for m in raw_body["messages"]:
            if isinstance(m, dict) and m.get("role") == "user":
                m["role"] = "human"

    try:
        query_req = QueryRequest.model_validate(raw_body)
    except Exception as e:
        print(f"[WARN]: QueryRequest validation failed, using raw fallback: {e}")
        query_req = None

    # Model routing: check user selection from workspace_options
    selected_model = None
    if query_req and query_req.workspace_options:
        selected_model = query_req.workspace_options.get("select-model")
    if not selected_model and isinstance(raw_body, dict):
        selected_model = raw_body.get("workspace_options", {}).get("select-model")

    target_model = selected_model or DEFAULT_MODEL
    print(f"[MODEL ROUTING]: Selected model ID = '{target_model}'")

    has_tool_results = False
    if query_req and query_req.messages:
        has_tool_results = any(
            isinstance(m, LlmClientFunctionCallResultMessage) or (isinstance(m, dict) and m.get("role") == "tool")
            for m in query_req.messages
        )
    elif isinstance(raw_body, dict) and "messages" in raw_body:
        has_tool_results = any(
            isinstance(m, dict) and m.get("role") == "tool"
            for m in raw_body.get("messages", [])
        )

    if query_req:
        clean_messages = build_openai_messages(query_req, has_tool_results)
    else:
        raw_messages = raw_body.get("messages", []) if isinstance(raw_body, dict) else []
        clean_messages = [
            {"role": "system", "content": "You are a professional financial AI assistant for OpenBB Workspace."}
        ]
        for m in raw_messages:
            if isinstance(m, dict):
                r = m.get("role", "user")
                clean_messages.append({"role": "user" if r in ["human", "user"] else "assistant", "content": str(m.get("content", ""))})

    active_tools = AGENT_TOOLS_PASS2 if has_tool_results else AGENT_TOOLS_PASS1

    async def stream_generator():
        headers = {
            "Authorization": f"Bearer {LITELLM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        status_msg = f"Synthesizing financial data with {target_model}..." if has_tool_results else f"Analyzing query using {target_model}..."
        initial_rs = reasoning_step(status_msg)
        yield {
            "event": initial_rs.event,
            "data": initial_rs.data if isinstance(initial_rs.data, str) else initial_rs.data.model_dump_json()
        }

        current_messages = list(clean_messages)
        max_internal_turns = 5
        turn_count = 0

        while turn_count < max_internal_turns:
            turn_count += 1
            sanitized_messages = sanitize_openai_messages(current_messages)

            litellm_payload = {
                "model": target_model,
                "messages": sanitized_messages,
                "tools": active_tools,
                "tool_choice": "auto",
                "stream": True
            }

            tool_calls_accumulator: Dict[int, Dict[str, Any]] = {}

            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    async with client.stream("POST", LITELLM_API_URL, json=litellm_payload, headers=headers) as response:
                        if response.status_code != 200:
                            err_bytes = await response.aread()
                            err_msg = f"[LiteLLM Error {response.status_code} ({target_model})]: {err_bytes.decode('utf-8', errors='ignore')}"
                            print(err_msg)
                            err_rs = reasoning_step(f"LiteLLM Error {response.status_code}", event_type="ERROR")
                            yield {
                                "event": err_rs.event,
                                "data": err_rs.data if isinstance(err_rs.data, str) else err_rs.data.model_dump_json()
                            }
                            mc = message_chunk(err_msg)
                            yield {
                                "event": mc.event,
                                "data": mc.data if isinstance(mc.data, str) else mc.data.model_dump_json()
                            }
                            return

                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk_json = json.loads(data_str)
                                choice = chunk_json.get("choices", [{}])[0]
                                delta = choice.get("delta", {})

                                content_delta = delta.get("content")
                                if content_delta:
                                    mc = message_chunk(content_delta)
                                    yield {
                                        "event": mc.event,
                                        "data": mc.data if isinstance(mc.data, str) else mc.data.model_dump_json()
                                    }

                                delta_tool_calls = delta.get("tool_calls", [])
                                for tc in delta_tool_calls:
                                    tc_idx = tc.get("index", 0)
                                    if tc_idx not in tool_calls_accumulator:
                                        tool_calls_accumulator[tc_idx] = {
                                            "id": tc.get("id", f"call_{uuid.uuid4().hex[:6]}"),
                                            "name": tc.get("function", {}).get("name", ""),
                                            "arguments": tc.get("function", {}).get("arguments", "")
                                        }
                                    else:
                                        if tc.get("id"):
                                            tool_calls_accumulator[tc_idx]["id"] = tc["id"]
                                        fn_delta = tc.get("function", {})
                                        if fn_delta.get("name"):
                                            tool_calls_accumulator[tc_idx]["name"] += fn_delta["name"]
                                        if fn_delta.get("arguments"):
                                            tool_calls_accumulator[tc_idx]["arguments"] += fn_delta["arguments"]

                            except json.JSONDecodeError:
                                continue

            except Exception as ex:
                print(f"[BRIDGE EXCEPTION]: {str(ex)}")
                err_rs = reasoning_step(f"Agent Bridge Exception: {str(ex)}", event_type="ERROR")
                yield {
                    "event": err_rs.event,
                    "data": err_rs.data if isinstance(err_rs.data, str) else err_rs.data.model_dump_json()
                }
                mc = message_chunk(f"[Bridge Error]: {str(ex)}")
                yield {
                    "event": mc.event,
                    "data": mc.data if isinstance(mc.data, str) else mc.data.model_dump_json()
                }
                return

            if not tool_calls_accumulator:
                print(f"[TURN {turn_count} COMPLETED]: Model '{target_model}' finished streaming.")
                break

            should_terminate_stream = False
            assistant_tool_calls_payload = []

            for idx, tc_data in tool_calls_accumulator.items():
                call_id = tc_data.get("id", f"call_{uuid.uuid4().hex[:6]}")
                fn_name = tc_data.get("name", "")
                raw_args = tc_data.get("arguments", "{}")
                args_dict = parse_tool_args(raw_args)

                print(f"[TOOL CALL DETECTED Turn {turn_count}]: {fn_name} -> {args_dict}")

                assistant_tool_calls_payload.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": raw_args
                    }
                })

                if fn_name == "get_widget_data":
                    data_sources = args_dict.get("data_sources", [])
                    fc_data = FunctionCallSSEData(
                        function="get_widget_data",
                        input_arguments={"data_sources": data_sources}
                    )
                    fc_sse = FunctionCallSSE(data=fc_data)
                    yield {
                        "event": fc_sse.event,
                        "data": fc_sse.data.model_dump_json(exclude_none=True)
                    }
                    should_terminate_stream = True

                elif fn_name == "create_table_artifact":
                    t_data = args_dict.get("data", [])
                    t_name = args_dict.get("name", "Financial Data Table")
                    t_desc = args_dict.get("description", "Structured table artifact")
                    tbl_sse = table(data=t_data, name=t_name, description=t_desc)
                    yield {
                        "event": tbl_sse.event,
                        "data": tbl_sse.data.model_dump_json(exclude_none=True)
                    }

                elif fn_name == "create_chart_artifact":
                    c_type = args_dict.get("type", "line")
                    c_data = args_dict.get("data", [])
                    c_name = args_dict.get("name", "Financial Chart")
                    c_desc = args_dict.get("description", "Chart visualization artifact")
                    c_x = args_dict.get("x_key")
                    c_y = args_dict.get("y_keys")
                    c_angle = args_dict.get("angle_key")
                    c_label = args_dict.get("callout_label_key")
                    
                    chart_sse = chart(
                        type=c_type,
                        data=c_data,
                        x_key=c_x,
                        y_keys=c_y,
                        angle_key=c_angle,
                        callout_label_key=c_label,
                        name=c_name,
                        description=c_desc,
                    )
                    yield {
                        "event": chart_sse.event,
                        "data": chart_sse.data.model_dump_json(exclude_none=True)
                    }

                elif fn_name == "prompt_suggestions":
                    suggestions_list = args_dict.get("suggestions", [])
                    if suggestions_list:
                        ps_sse = prompt_suggestions(suggestions_list)
                        yield {
                            "event": ps_sse.event,
                            "data": ps_sse.data.model_dump_json(exclude_none=True)
                        }

            if should_terminate_stream:
                return

            current_messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": assistant_tool_calls_payload
            })
            for tc in assistant_tool_calls_payload:
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"status": "success", "message": f"Executed tool {tc['function']['name']} successfully"})
                })

    return EventSourceResponse(stream_generator())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=32001)
