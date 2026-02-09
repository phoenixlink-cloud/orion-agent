"""
Orion Agent — Voice Integrations (v6.4.0)

Base classes and provider registry for Text-to-Speech and Speech-to-Text.
TTS Providers: OpenAI TTS, ElevenLabs, Google Cloud TTS, Azure TTS, etc.
STT Providers: OpenAI Whisper, Google Cloud STT, Azure STT, etc.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orion.integrations.voice")


class TTSProviderBase(ABC):
    """Base class for Text-to-Speech providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def supported_voices(self) -> List[str]:
        return []

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "default", **kwargs) -> Dict[str, Any]:
        """
        Convert text to speech audio.

        Returns:
            Dict with 'success', 'audio' (bytes or URL), 'format', 'error'
        """
        ...


class STTProviderBase(ABC):
    """Base class for Speech-to-Text providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def supported_languages(self) -> List[str]:
        return ["en"]

    @abstractmethod
    async def transcribe(self, audio: bytes, language: str = "en", **kwargs) -> Dict[str, Any]:
        """
        Transcribe audio to text.

        Returns:
            Dict with 'success', 'text', 'language', 'error'
        """
        ...


class OpenAITTSProvider(TTSProviderBase):
    """OpenAI TTS (tts-1, tts-1-hd)."""

    @property
    def name(self) -> str:
        return "openai_tts"

    @property
    def supported_voices(self) -> List[str]:
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    async def synthesize(self, text: str, voice: str = "alloy", **kwargs) -> Dict[str, Any]:
        import httpx

        try:
            from orion.security.store import SecureStore
            api_key = SecureStore().get_key("openai")
        except Exception:
            api_key = None

        if not api_key:
            return {"success": False, "error": "OpenAI API key not configured for TTS."}

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": kwargs.get("model", "tts-1"),
            "input": text[:4096],
            "voice": voice,
            "response_format": kwargs.get("format", "mp3"),
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload)
            resp.raise_for_status()

        return {"success": True, "audio": resp.content, "format": payload["response_format"]}


class OpenAISTTProvider(STTProviderBase):
    """OpenAI Whisper speech-to-text."""

    @property
    def name(self) -> str:
        return "openai_stt"

    @property
    def supported_languages(self) -> List[str]:
        return ["en", "es", "fr", "de", "it", "pt", "nl", "ja", "zh", "ko"]

    async def transcribe(self, audio: bytes, language: str = "en", **kwargs) -> Dict[str, Any]:
        import httpx

        try:
            from orion.security.store import SecureStore
            api_key = SecureStore().get_key("openai")
        except Exception:
            api_key = None

        if not api_key:
            return {"success": False, "error": "OpenAI API key not configured for Whisper."}

        headers = {"Authorization": f"Bearer {api_key}"}
        files = {"file": ("audio.wav", audio, "audio/wav")}
        data = {"model": "whisper-1", "language": language}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers, files=files, data=data,
            )
            resp.raise_for_status()
            result = resp.json()

        return {"success": True, "text": result.get("text", ""), "language": language}


# ── Provider registries ──────────────────────────────────────────────────

_TTS_PROVIDERS: Dict[str, TTSProviderBase] = {}
_STT_PROVIDERS: Dict[str, STTProviderBase] = {}


def register_tts_provider(provider: TTSProviderBase):
    _TTS_PROVIDERS[provider.name] = provider


def register_stt_provider(provider: STTProviderBase):
    _STT_PROVIDERS[provider.name] = provider


def get_tts_provider(name: str = "openai_tts") -> Optional[TTSProviderBase]:
    return _TTS_PROVIDERS.get(name)


def get_stt_provider(name: str = "openai_stt") -> Optional[STTProviderBase]:
    return _STT_PROVIDERS.get(name)


def list_tts_providers() -> List[str]:
    return list(_TTS_PROVIDERS.keys())


def list_stt_providers() -> List[str]:
    return list(_STT_PROVIDERS.keys())


# Auto-register default providers
register_tts_provider(OpenAITTSProvider())
register_stt_provider(OpenAISTTProvider())
