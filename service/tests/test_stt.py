import pytest
from groq import GroqError

from src.pipeline import stt
from src.pipeline.errors import UpstreamUnavailable


class _FakeTranscription:
    def __init__(self, text: str):
        self.text = text


class _FakeTranscriptions:
    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeTranscription(self._text)


class _FakeAudio:
    def __init__(self, text: str):
        self.transcriptions = _FakeTranscriptions(text)


class _FakeClient:
    def __init__(self, text: str):
        self.audio = _FakeAudio(text)


async def test_transcribe_sends_station_name_prompt(monkeypatch):
    client = _FakeClient("when is the next train from Richmond to Flinders Street")
    monkeypatch.setattr(stt, "_get_client", lambda: client)

    result = await stt.transcribe(b"fake audio bytes")

    assert result == "when is the next train from Richmond to Flinders Street"
    call = client.audio.transcriptions.calls[0]
    assert call["prompt"] == stt._STATION_NAME_PROMPT
    assert len(stt._STATION_NAME_PROMPT) <= 896


class _RaisingTranscriptions:
    async def create(self, **kwargs):
        raise GroqError("boom")


class _RaisingAudio:
    def __init__(self):
        self.transcriptions = _RaisingTranscriptions()


class _RaisingClient:
    def __init__(self):
        self.audio = _RaisingAudio()


async def test_raises_upstream_unavailable_when_groq_request_fails(monkeypatch):
    monkeypatch.setattr(stt, "_get_client", lambda: _RaisingClient())
    with pytest.raises(UpstreamUnavailable):
        await stt.transcribe(b"fake audio bytes")
