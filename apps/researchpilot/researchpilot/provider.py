import json
import math
from urllib.parse import urlparse

import httpx


class ProviderError(ValueError):
    pass


class ModelProvider:
    def __init__(self, settings):
        self.settings = settings
        parsed = urlparse(settings.api_base)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ProviderError("模型服务地址必须为 HTTPS，或本机 HTTP 地址。")

    def post(self, path, payload):
        headers = {"Authorization": f"Bearer {self.settings.api_key}"} if self.settings.api_key else {}
        try:
            with httpx.Client(timeout=60, follow_redirects=False) as client:
                response = client.post(self.settings.api_base + path, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"模型服务返回 HTTP {exc.response.status_code}，请检查服务地址、模型名称、余额和密钥。") from None
        except (httpx.HTTPError, ValueError):
            raise ProviderError("模型服务连接失败或响应无效，请检查网络和配置。") from None

    def chat(self, messages, tools, allow_tools=True):
        if not self.settings.model:
            raise ProviderError("请在 .env 设置 RP_MODEL，然后重启服务。")
        payload = {"model": self.settings.model, "messages": messages, "tools": tools,
                   "tool_choice": "auto" if allow_tools else "none"}
        result = self.post("/chat/completions", payload)
        try:
            message = result["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError()
            return message, result.get("usage") or {}
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("模型没有返回有效的 Chat Completions 消息。") from None

    def embed(self, texts):
        result = self.post("/embeddings", {"model": self.settings.embed_model, "input": texts})
        try:
            data = sorted(result["data"], key=lambda x: x["index"])
            vectors = [d["embedding"] for d in data]
            if len(vectors) != len(texts) or not vectors:
                raise ValueError()
            size = len(vectors[0])
            if not size or any(len(v) != size or not all(isinstance(x, (float, int)) and math.isfinite(x) for x in v) for v in vectors):
                raise ValueError()
            return vectors
        except (KeyError, TypeError, ValueError):
            raise ProviderError("Embedding 服务返回的向量数量或格式无效。") from None
