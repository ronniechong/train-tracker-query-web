import base64

import pytest
from groq import GroqError

from src.pipeline import tts
from src.pipeline.errors import UpstreamUnavailable


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeSpeech:
    def __init__(self, data: bytes):
        self._data = data
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._data)


class _FakeAudio:
    def __init__(self, data: bytes):
        self.speech = _FakeSpeech(data)


class _FakeClient:
    def __init__(self, data: bytes):
        self.audio = _FakeAudio(data)


async def test_returns_base64_encoded_audio(monkeypatch):
    raw = b"RIFF....WAVEfmt "
    client = _FakeClient(raw)
    monkeypatch.setattr(tts, "_get_client", lambda: client)

    result = await tts.synthesize("hello")

    assert base64.b64decode(result) == raw
    assert client.audio.speech.calls[0]["input"] == "hello"
    assert client.audio.speech.calls[0]["response_format"] == "wav"


class _RaisingSpeech:
    async def create(self, **kwargs):
        raise GroqError("boom")


class _RaisingAudio:
    def __init__(self):
        self.speech = _RaisingSpeech()


class _RaisingClient:
    def __init__(self):
        self.audio = _RaisingAudio()


async def test_raises_upstream_unavailable_when_groq_request_fails(monkeypatch):
    monkeypatch.setattr(tts, "_get_client", lambda: _RaisingClient())
    with pytest.raises(UpstreamUnavailable):
        await tts.synthesize("hello")
