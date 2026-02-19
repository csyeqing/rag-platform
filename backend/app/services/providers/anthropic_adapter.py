from __future__ import annotations

from collections.abc import Iterator
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


class AnthropicAdapter(ProviderAdapter):
    provider_name = 'anthropic'

    def _client(self) -> httpx.Client:
        settings = get_settings()
        return httpx.Client(timeout=settings.request_timeout_seconds)

    def _message_url(self, endpoint: str) -> str:
        if endpoint.rstrip('/').endswith('/v1/messages'):
            return endpoint
        return urljoin(endpoint.rstrip('/') + '/', 'v1/messages')

    def validate_credentials(self, config: ProviderConfigDTO) -> ValidationResult:
        if not config.endpoint_url or not config.model_name or not config.api_key:
            return ValidationResult(valid=False, message='endpoint/model/api_key 不能为空')
        return ValidationResult(
            valid=True,
            message='Anthropic 配置格式有效',
            capabilities={'chat': True, 'embed': False, 'rerank': False},
        )

    def chat_stream(self, config: ProviderConfigDTO, req: ChatRequest) -> Iterator[ChatDelta]:
        content = self.chat(config, req).content
        for piece in content.split(' '):
            yield ChatDelta(delta=f'{piece} ')

    def chat(self, config: ProviderConfigDTO, req: ChatRequest) -> ChatResponse:
        if not config.endpoint_url.startswith('http'):
            return ChatResponse(content='Anthropic 模拟回复：请配置可访问的 endpoint_url 后重试。')

        system_text = ''
        messages = []
        for message in req.messages:
            role = message.get('role')
            if role == 'system':
                system_text = message.get('content', '')
                continue
            if role in {'user', 'assistant'}:
                messages.append({'role': role, 'content': message.get('content', '')})

        payload = {
            'model': req.model,
            'messages': messages,
            'max_tokens': req.max_tokens,
            'temperature': req.temperature,
            'top_p': req.top_p,
        }
        if system_text:
            payload['system'] = system_text

        headers = {
            'x-api-key': config.api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }

        try:
            with self._client() as client:
                response = client.post(self._message_url(config.endpoint_url), headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
                content_parts = body.get('content', [])
                text_parts = [part.get('text', '') for part in content_parts if isinstance(part, dict)]
                if text_parts:
                    return ChatResponse(content=''.join(text_parts))
        except Exception:
            pass

        return ChatResponse(content='Anthropic 调用失败，已降级为本地回复。')

    def embed(self, config: ProviderConfigDTO, req: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[hash_embedding(text) for text in req.texts])

    def rerank(self, config: ProviderConfigDTO, req: RerankRequest) -> RerankResponse:
        scored = [
            RerankItem(index=index, score=token_overlap_score(req.query, doc))
            for index, doc in enumerate(req.documents)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return RerankResponse(items=scored)
