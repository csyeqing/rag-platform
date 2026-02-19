from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import quote

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


class GeminiAdapter(ProviderAdapter):
    provider_name = 'gemini'

    def _client(self) -> httpx.Client:
        settings = get_settings()
        return httpx.Client(timeout=settings.request_timeout_seconds)

    def _chat_url(self, endpoint: str, model: str, api_key: str) -> str:
        base = endpoint.rstrip('/')
        return f"{base}/v1beta/models/{quote(model)}:generateContent?key={api_key}"

    def validate_credentials(self, config: ProviderConfigDTO) -> ValidationResult:
        if not config.endpoint_url or not config.model_name or not config.api_key:
            return ValidationResult(valid=False, message='endpoint/model/api_key 不能为空')
        return ValidationResult(
            valid=True,
            message='Gemini 配置格式有效',
            capabilities={'chat': True, 'embed': False, 'rerank': False},
        )

    def chat_stream(self, config: ProviderConfigDTO, req: ChatRequest) -> Iterator[ChatDelta]:
        content = self.chat(config, req).content
        for piece in content.split(' '):
            yield ChatDelta(delta=f'{piece} ')

    def chat(self, config: ProviderConfigDTO, req: ChatRequest) -> ChatResponse:
        if not config.endpoint_url.startswith('http'):
            return ChatResponse(content='Gemini 模拟回复：请配置可访问的 endpoint_url 后重试。')

        joined_content = '\n'.join(str(item.get('content', '')) for item in req.messages)
        payload = {
            'contents': [
                {
                    'parts': [
                        {
                            'text': joined_content,
                        }
                    ]
                }
            ],
            'generationConfig': {
                'temperature': req.temperature,
                'topP': req.top_p,
                'maxOutputTokens': req.max_tokens,
            },
        }

        try:
            with self._client() as client:
                response = client.post(
                    self._chat_url(config.endpoint_url, req.model, config.api_key),
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                candidates = body.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    text = ''.join(part.get('text', '') for part in parts if isinstance(part, dict))
                    if text:
                        return ChatResponse(content=text)
        except Exception:
            pass

        return ChatResponse(content='Gemini 调用失败，已降级为本地回复。')

    def embed(self, config: ProviderConfigDTO, req: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[hash_embedding(text) for text in req.texts])

    def rerank(self, config: ProviderConfigDTO, req: RerankRequest) -> RerankResponse:
        scored = [
            RerankItem(index=index, score=token_overlap_score(req.query, doc))
            for index, doc in enumerate(req.documents)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return RerankResponse(items=scored)
