class UpstreamUnavailable(Exception):
    """A Groq API call failed with no graceful degrade available (unlike
    gate2's suggestion call, which falls back to no-suggestion) - the
    pipeline stage cannot proceed without this result."""
