from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class ProviderConfigDTO:
    provider_type: str
    endpoint_url: str
    model_name: str
    api_key: str


@dataclass
class ChatRequest:
    model: str
    messages: list[dict]
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 1024


@dataclass
class ChatDelta:
    delta: str


@dataclass
class ChatResponse:
    content: str


@dataclass
class EmbeddingRequest:
    model: str
    texts: list[str]


@dataclass
class EmbeddingResponse:
    vectors: list[list[float]]


@dataclass
class RerankRequest:
    model: str
    query: str
    documents: list[str]


@dataclass
class RerankItem:
    index: int
    score: float


@dataclass
class RerankResponse:
    items: list[RerankItem] = field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    message: str
    capabilities: dict = field(default_factory=dict)


class ProviderAdapter(ABC):
    provider_name: str = 'unknown'

    @abstractmethod
    def validate_credentials(self, config: ProviderConfigDTO) -> ValidationResult:
        raise NotImplementedError

    @abstractmethod
    def chat_stream(self, config: ProviderConfigDTO, req: ChatRequest) -> Iterator[ChatDelta]:
        raise NotImplementedError

    @abstractmethod
    def chat(self, config: ProviderConfigDTO, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    @abstractmethod
    def embed(self, config: ProviderConfigDTO, req: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError

    @abstractmethod
    def rerank(self, config: ProviderConfigDTO, req: RerankRequest) -> RerankResponse:
        raise NotImplementedError
