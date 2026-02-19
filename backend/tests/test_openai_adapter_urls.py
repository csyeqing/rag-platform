from app.services.providers.openai_adapter import OpenAIAdapter


def test_chat_url_with_openai_base() -> None:
    adapter = OpenAIAdapter()
    assert adapter._chat_url('https://api.openai.com') == 'https://api.openai.com/v1/chat/completions'


def test_chat_url_with_v1_base() -> None:
    adapter = OpenAIAdapter()
    assert adapter._chat_url('https://api.openai.com/v1') == 'https://api.openai.com/v1/chat/completions'


def test_chat_url_with_non_v1_version_base() -> None:
    adapter = OpenAIAdapter()
    assert (
        adapter._chat_url('https://open.bigmodel.cn/api/paas/v4')
        == 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
    )


def test_embed_url_with_non_v1_version_base() -> None:
    adapter = OpenAIAdapter()
    assert (
        adapter._embed_url('https://open.bigmodel.cn/api/paas/v4')
        == 'https://open.bigmodel.cn/api/paas/v4/embeddings'
    )
