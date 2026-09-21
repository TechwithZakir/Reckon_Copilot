DEFAULT_TTLS = {
    "context.read": 60,
    "knowledge.read": 300,
    "analytics.run": 600,
    "provider.call": 900,
}


def ttl_for(capability: str, default: int = 300) -> int:
    return DEFAULT_TTLS.get(capability, default)
