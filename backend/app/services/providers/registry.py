from __future__ import annotations

from app.services.providers.anthropic_adapter import AnthropicAdapter
from app.services.providers.base import ProviderAdapter
from app.services.providers.gemini_adapter import GeminiAdapter
from app.services.providers.openai_adapter import OpenAIAdapter
from app.services.providers.openai_compatible_adapter import OpenAICompatibleAdapter


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {
            'openai': OpenAIAdapter(),
            'anthropic': AnthropicAdapter(),
            'gemini': GeminiAdapter(),
            'openai_compatible': OpenAICompatibleAdapter(),
        }

    def get(self, provider_type: str) -> ProviderAdapter:
        if provider_type not in self._adapters:
            raise ValueError(f'Unsupported provider_type: {provider_type}')
        return self._adapters[provider_type]


provider_registry = ProviderRegistry()
