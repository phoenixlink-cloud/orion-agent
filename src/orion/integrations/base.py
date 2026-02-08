"""
Orion Agent — Integration Base Class (v6.4.0)

Abstract base class that all integrations must implement.
Provides a standard interface for discovery, authentication,
capability reporting, and lifecycle management.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class AuthType(Enum):
    """Authentication method required by an integration."""
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"


class IntegrationStatus(Enum):
    """Current status of an integration."""
    DISABLED = "disabled"
    AVAILABLE = "available"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


@dataclass
class IntegrationCapability:
    """A single capability that an integration provides."""
    name: str
    description: str
    category: str  # e.g. "image_gen", "voice", "docs", "storage"
    requires_auth: bool = True


@dataclass
class IntegrationInfo:
    """Metadata about an integration for display/API purposes."""
    name: str
    display_name: str
    description: str
    version: str
    auth_type: AuthType
    status: IntegrationStatus
    capabilities: List[str]
    config: Dict[str, Any] = field(default_factory=dict)


class IntegrationBase(ABC):
    """
    Abstract base class for all Orion integrations.

    Every integration must implement:
    - name, display_name, description, version properties
    - auth_type property
    - setup() — one-time initialization
    - teardown() — cleanup
    - is_available() — can this integration be used right now?
    - get_capabilities() — what can this integration do?
    - get_status() — current status
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this integration (snake_case)."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what this integration does."""
        ...

    @property
    def version(self) -> str:
        """Integration version."""
        return "1.0.0"

    @property
    @abstractmethod
    def auth_type(self) -> AuthType:
        """What authentication does this integration require?"""
        ...

    @abstractmethod
    def setup(self) -> bool:
        """
        Initialize the integration.

        Returns True if setup succeeded, False otherwise.
        Called once when the integration is first loaded.
        """
        ...

    def teardown(self) -> None:
        """Clean up resources. Called when integration is unloaded."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this integration can be used right now.

        For API_KEY auth: checks if key is stored.
        For OAUTH auth: checks if token is valid.
        For NONE: checks if underlying service is reachable.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> List[IntegrationCapability]:
        """Return list of capabilities this integration provides."""
        ...

    def get_status(self) -> IntegrationStatus:
        """Get current status of this integration."""
        try:
            if not self.is_available():
                return IntegrationStatus.AVAILABLE
            return IntegrationStatus.AUTHENTICATED
        except Exception:
            return IntegrationStatus.ERROR

    def get_info(self) -> IntegrationInfo:
        """Get full metadata about this integration."""
        return IntegrationInfo(
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            version=self.version,
            auth_type=self.auth_type,
            status=self.get_status(),
            capabilities=[c.name for c in self.get_capabilities()],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize integration info for API responses."""
        info = self.get_info()
        return {
            "name": info.name,
            "display_name": info.display_name,
            "description": info.description,
            "version": info.version,
            "auth_type": info.auth_type.value,
            "status": info.status.value,
            "capabilities": info.capabilities,
            "config": info.config,
        }
