"""One function, generate, in front of whichever chat model is in use.

By default generate() calls the deterministic stand-in of llm_standin.py, so
that every script in this chapter and the next runs offline and reproduces the
same numbers. A hosted model is used only when the environment says so:

    LLM_PROVIDER=anthropic  LLM_MODEL=<model id>  ANTHROPIC_API_KEY=...
    LLM_PROVIDER=openai     LLM_MODEL=<model id>  OPENAI_API_KEY=...

The provider SDKs (anthropic, openai) are imported only when selected, and are
listed as optional in requirements.txt. Pin LLM_MODEL to a dated model version:
a change of model is a release, and the evaluation should be rerun.
"""
import os

_offline = None


def offline_model():
    """The model used when no hosted provider is configured."""
    global _offline
    if _offline is None:
        from llm_standin import StandIn
        _offline = StandIn()
    return _offline


def use_offline(model):
    """Replace the offline model (any object with a generate method); returns the old one."""
    global _offline
    previous, _offline = _offline, model
    return previous


def provider():
    name = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if name in ("anthropic", "openai") and os.environ.get("LLM_MODEL"):
        return name
    return "offline"


def model_name():
    if provider() == "offline":
        return getattr(offline_model(), "name", "offline")
    return f"{provider()}:{os.environ['LLM_MODEL']}"


def generate(system, user, max_tokens=700, temperature=0):
    """Return the model's text for one system prompt and one user message."""
    name = provider()
    if name == "anthropic":
        return _anthropic(system, user, max_tokens, temperature)
    if name == "openai":
        return _openai(system, user, max_tokens, temperature)
    return offline_model().generate(system=system, user=user, max_tokens=max_tokens,
                                    temperature=temperature)


def _anthropic(system, user, max_tokens, temperature):
    import anthropic                                   # optional dependency
    client = anthropic.Anthropic()                     # reads ANTHROPIC_API_KEY
    kwargs = {"model": os.environ["LLM_MODEL"], "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": user}]}
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = client.messages.create(**kwargs)
    return "".join(block.text for block in response.content if block.type == "text")


def _openai(system, user, max_tokens, temperature):
    import openai                                      # optional dependency
    client = openai.OpenAI()                           # reads OPENAI_API_KEY
    kwargs = {"model": os.environ["LLM_MODEL"], "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]}
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content
