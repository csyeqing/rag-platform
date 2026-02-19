from __future__ import annotations

from app.services.providers.openai_adapter import OpenAIAdapter


class OpenAICompatibleAdapter(OpenAIAdapter):
    provider_name = 'openai_compatible'
