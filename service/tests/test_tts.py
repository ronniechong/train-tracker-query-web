import base64

from src.pipeline import tts


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
