"""Minimal DeepSeek non-thinking Chat Completions adapter, with no retries."""

import json

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


class ModelFailure(Exception):
    def __init__(self, code, *, http_status=None, transport_error=None):
        self.code = code
        self.http_status = http_status
        self.transport_error = transport_error
        super().__init__(code)


class DeepSeekModel:
    def __init__(self, settings):
        self.settings = settings

    async def ainvoke(self, messages, tools):
        converted = []
        for message in messages:
            if isinstance(message, ToolMessage):
                converted.append(
                    {
                        "role": "tool",
                        "content": message.content,
                        "tool_call_id": message.tool_call_id,
                    }
                )
            elif isinstance(message, AIMessage):
                item = {"role": "assistant", "content": message.content or None}
                if message.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["args"], ensure_ascii=False),
                            },
                        }
                        for call in message.tool_calls
                    ]
                converted.append(item)
            elif isinstance(message, (SystemMessage, HumanMessage)):
                converted.append(
                    {
                        "role": "system" if isinstance(message, SystemMessage) else "user",
                        "content": message.content,
                    }
                )
            else:
                raise ModelFailure("invalid_message")
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                response = await client.post(
                    self.settings.model_base_url.rstrip("/") + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + self.settings.model_api_key.get_secret_value()
                    },
                    json={
                        "model": self.settings.model_name,
                        "messages": converted,
                        "tools": tools,
                        "thinking": {"type": "disabled"},
                        "max_tokens": 2048,
                        "stream": False,
                    },
                )
                if response.status_code != 200:
                    raise ModelFailure("model_unavailable", http_status=response.status_code)
                body = response.json()
                raw = body["choices"][0]["message"]
                calls = [
                    {
                        "id": call["id"],
                        "name": call["function"]["name"],
                        "args": json.loads(call["function"]["arguments"]),
                        "type": "tool_call",
                    }
                    for call in raw.get("tool_calls", [])
                ]
                usage = body.get("usage")
                return AIMessage(
                    content=raw.get("content") or "",
                    tool_calls=calls,
                    response_metadata={"model_name": body.get("model")},
                    usage_metadata=(
                        {
                            "input_tokens": usage["prompt_tokens"],
                            "output_tokens": usage["completion_tokens"],
                            "total_tokens": usage["total_tokens"],
                        }
                        if usage
                        else None
                    ),
                )
        except httpx.TimeoutException:
            raise ModelFailure("model_timeout", transport_error="timeout") from None
        except ModelFailure:
            raise
        except httpx.HTTPError:
            raise ModelFailure("model_unavailable", transport_error="http_error") from None
        except (ValueError, KeyError, TypeError):
            raise ModelFailure("model_unavailable", transport_error="invalid_response") from None
