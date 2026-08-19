"""Provider factory."""
import config


def make_provider(name: str | None = None):
    name = name or config.LLM_PROVIDER
    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "fake":
        from .fake_provider import FakeProvider
        return FakeProvider()
    raise ValueError(f"Unknown provider: {name}")
