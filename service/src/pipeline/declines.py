import random

# Pre-written so a Gate 1 rejection never costs a live composition or TTS
# call for text that never varies. Rotated so it doesn't sound identical
# every time; audio for each gets pre-synthesized once TTS lands, not at
# request time.
CANNED_DECLINES = (
    "I can only help with Melbourne metro train times.",
    "Sorry, that's outside what I can help with — I only answer Melbourne train schedule questions.",
    "I'm just for Melbourne train times, so I can't help with that one.",
)


def random_decline() -> str:
    return random.choice(CANNED_DECLINES)
