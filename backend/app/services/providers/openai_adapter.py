from __future__ import annotations

import json
import logging
from collections.abc import Iterator
import re
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings
from app.services.providers.base import (
    ChatDelta,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ProviderAdapter,
    ProviderConfigDTO,
    RerankItem,
    RerankRequest,
    RerankResponse,
    ValidationResult,
)
from app.services.providers.local_algorithms import hash_embedding, token_overlap_score


class OpenAIAdapter(ProviderAdapter):
    provider_name = 'openai'

    def _client(self) -> httpx.Client:
        settings = get_settings()
        return httpx.Client(timeout=settings.request_timeout_seconds)

    def _stream_client(self) -> httpx.Client:
        settings = get_settings()
        return httpx.Client(timeout=settings.request_timeout_seconds * 10)

    @staticmethod
    def _has_version_suffix(endpoint: str) -> bool:
        return bool(re.search(r'/v\d+(?:\.\d+)?$', endpoint.rstrip('/')))

    def _chat_url(self, endpoint: str) -> str:
        base = endpoint.rstrip('/')
        if base.endswith('/chat/completions'):
            return base
        if self._has_version_suffix(base):
            return f'{base}/chat/completions'
        return urljoin(base + '/', 'v1/chat/completions')

    def _embed_url(self, endpoint: str) -> str:
        base = endpoint.rstrip('/')
        if base.endswith('/embeddings'):
            return base
        if self._has_version_suffix(base):
            return f'{base}/embeddings'
        return urljoin(base + '/', 'v1/embeddings')

    def validate_credentials(self, config: ProviderConfigDTO) -> ValidationResult:
        if not config.endpoint_url or not config.model_name or not config.api_key:
            return ValidationResult(valid=False, message='endpoint/model/api_key 不能为空')
        return ValidationResult(
            valid=True,
            message='配置格式有效',
            capabilities={'chat': True, 'embed': True, 'rerank': False},
        )

    def chat_stream(self, config: ProviderConfigDTO, req: ChatRequest) -> Iterator[ChatDelta]:
        if not config.endpoint_url.startswith('http'):
            # 非 HTTP 端点使用模拟流式
            full = self._fallback_chat(req).content
            for token in full.split(' '):
                yield ChatDelta(delta=f'{token} ')
            return

        payload = {
            'model': req.model,
            'messages': req.messages,
            'temperature': req.temperature,
            'top_p': req.top_p,
            'max_tokens': req.max_tokens,
            'stream': True,
        }
        headers = {'Authorization': f'Bearer {config.api_key}', 'Content-Type': 'application/json'}

        try:
            with self._stream_client() as client:
                with client.stream('POST', self._chat_url(config.endpoint_url), headers=headers, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or not line.startswith('data: '):
                            continue
                        data = line[6:]  # 去掉 'data: ' 前缀
                        if data.strip() == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if delta:
                                yield ChatDelta(delta=delta)
                        except json.JSONDecodeError:
                            continue
        except Exception:
            # 流式失败时回退到非流式
            full = self.chat(config, req).content
            for token in full.split(' '):
                yield ChatDelta(delta=f'{token} ')

    def chat(self, config: ProviderConfigDTO, req: ChatRequest) -> ChatResponse:
        if not config.endpoint_url.startswith('http'):
            return self._fallback_chat(req)

        payload = {
            'model': req.model,
            'messages': req.messages,
            'temperature': req.temperature,
            'top_p': req.top_p,
            'max_tokens': req.max_tokens,
        }
        headers = {'Authorization': f'Bearer {config.api_key}', 'Content-Type': 'application/json'}

        try:
            with self._client() as client:
                response = client.post(self._chat_url(config.endpoint_url), headers=headers, json=payload)
                logging.getLogger('app.request').info(f'LLM response status: {response.status_code}, body: {response.text[:200]}')
                response.raise_for_status()
                body = response.json()
                message = body.get('choices', [{}])[0].get('message', {})
                content = message.get('content', '')
                if not content:
                    content = '模型返回了空结果，请检查参数。'
                if isinstance(content, list):
                    content = ''.join(item.get('text', '') for item in content if isinstance(item, dict))
                return ChatResponse(content=str(content))
        except Exception as e:
            logging.getLogger('app.request').error(f'LLM API call failed: {e}')
            return self._fallback_chat(req)

    def embed(self, config: ProviderConfigDTO, req: EmbeddingRequest) -> EmbeddingResponse:
        if not req.texts:
            return EmbeddingResponse(vectors=[])
        if not config.endpoint_url.startswith('http'):
            return EmbeddingResponse(vectors=[hash_embedding(text) for text in req.texts])

        payload = {'model': req.model, 'input': req.texts}
        headers = {'Authorization': f'Bearer {config.api_key}', 'Content-Type': 'application/json'}

        try:
            with self._client() as client:
                response = client.post(self._embed_url(config.endpoint_url), headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
                vectors = [item['embedding'] for item in body.get('data', [])]
                if vectors:
                    return EmbeddingResponse(vectors=vectors)
        except Exception:
            pass

        return EmbeddingResponse(vectors=[hash_embedding(text) for text in req.texts])

    def rerank(self, config: ProviderConfigDTO, req: RerankRequest) -> RerankResponse:
        scored = [
            RerankItem(index=index, score=token_overlap_score(req.query, doc))
            for index, doc in enumerate(req.documents)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return RerankResponse(items=scored)

    def _fallback_chat(self, req: ChatRequest) -> ChatResponse:
        user_input = ''
        context_json = '[]'
        for message in req.messages:
            if message.get('role') == 'user':
                user_input = message.get('content', '')
            if message.get('role') == 'system' and 'RAG_CONTEXT=' in message.get('content', ''):
                context_json = message.get('content', '').split('RAG_CONTEXT=', 1)[-1]

        references = []
        try:
            references = json.loads(context_json)
        except Exception:
            references = []

        if references:
            summary = '；'.join(item.get('snippet', '')[:80] for item in references[:3])
            content = f"基于知识库检索结果，问题是：{user_input}\n参考摘要：{summary}\n建议你进一步核对引用来源。"
        else:
            content = (
                f"知识库未命中，已切换为模型直答模式（模拟）。你的问题是：{user_input}。"
                "建议结合业务上下文进一步确认。"
            )
        return ChatResponse(content=content)
