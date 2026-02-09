"""
Orion Agent — Image Generation Integrations (v6.4.0)

Base class and provider registry for image generation services.
Providers: DALL-E 3, Stability AI, SDXL, Midjourney (via proxy), etc.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orion.integrations.image")


class ImageProviderBase(ABC):
    """Base class for image generation providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def supported_sizes(self) -> List[str]:
        return ["1024x1024"]

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate image(s) from a text prompt.

        Returns:
            Dict with 'success', 'images' (list of URLs or base64), 'error'
        """
        ...

    async def health_check(self) -> bool:
        return True


class DallEProvider(ImageProviderBase):
    """OpenAI DALL-E 3 image generation."""

    @property
    def name(self) -> str:
        return "dalle"

    @property
    def supported_sizes(self) -> List[str]:
        return ["1024x1024", "1792x1024", "1024x1792"]

    async def generate(self, prompt: str, size: str = "1024x1024", n: int = 1, **kwargs) -> Dict[str, Any]:
        import httpx

        try:
            from orion.security.store import SecureStore
            api_key = SecureStore().get_key("openai")
        except Exception:
            api_key = None

        if not api_key:
            return {"success": False, "error": "OpenAI API key not configured for DALL-E."}

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,  # DALL-E 3 only supports n=1
            "size": size,
            "quality": kwargs.get("quality", "standard"),
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        images = [item.get("url", "") for item in data.get("data", [])]
        return {"success": True, "images": images, "revised_prompt": data["data"][0].get("revised_prompt", "")}


# ── Provider registry ────────────────────────────────────────────────────

_PROVIDERS: Dict[str, ImageProviderBase] = {}


def register_image_provider(provider: ImageProviderBase):
    _PROVIDERS[provider.name] = provider


def get_image_provider(name: str = "dalle") -> Optional[ImageProviderBase]:
    return _PROVIDERS.get(name)


def list_image_providers() -> List[str]:
    return list(_PROVIDERS.keys())


# Auto-register default provider
register_image_provider(DallEProvider())
