"""API list prices, US dollars per million tokens: what a build's calls would cost on the API.

On a Claude subscription `claude -p` reports the same API-equivalent figure; it is usage,
not a bill. Cache writes are priced at 1.25× input (the five-minute cache).
"""

PRICES = {
    "opus": {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0},
    "sonnet": {"input": 2.0, "output": 10.0, "cache_read": 0.20, "cache_write": 2.5},
}
API_IDS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5"}
DEFAULT = "opus"


def family(model: str | None) -> str:
    """"opus", "sonnet", … from a model name or id; claude -p's default model counts as opus."""
    m = (model or "").lower()
    return next((f for f in PRICES if f in m), DEFAULT)


def api_id(model: str | None) -> str:
    """The API's id for "opus" or "sonnet" (claude -p's default counts as opus); an id is kept."""
    return API_IDS.get(model or DEFAULT, model)


def cost(usage: dict, model: str | None) -> float:
    p = PRICES[family(model)]
    return (usage.get("input_tokens", 0) * p["input"] + usage.get("output_tokens", 0) * p["output"]
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
            + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]) / 1e6
