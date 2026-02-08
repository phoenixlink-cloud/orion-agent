"""
Production Infrastructure — Health probes, metrics, graceful shutdown.

Provides K8s-compatible health endpoints, Prometheus metrics,
structured logging, rate limiting, and CI/CD generation.
"""

from orion.core.production.health import HealthProbe, HealthStatus
from orion.core.production.metrics import MetricsCollector, RateLimiter
from orion.core.production.shutdown import GracefulShutdown
from orion.core.production.logging import StructuredLogger


class ProductionStack:
    """Assembles all production infrastructure components."""

    def __init__(self, version: str = "6.4.0"):
        self.health = HealthProbe(version)
        self.metrics = MetricsCollector()
        self.shutdown = GracefulShutdown()
        self.logger = StructuredLogger()
        self.rate_limiter = RateLimiter()

        self.shutdown.set_health_probe(self.health)

    def start(self):
        """Start all production components."""
        self.shutdown.install_signal_handlers()
        self.health.mark_ready()
        self.logger.info("Production stack started")

    def stop(self):
        """Stop all production components."""
        self.shutdown.shutdown()
        self.logger.info("Production stack stopped")


def get_production_stack(version: str = "6.4.0") -> ProductionStack:
    """Factory function to create a ProductionStack."""
    return ProductionStack(version)


__all__ = [
    "HealthProbe", "HealthStatus", "MetricsCollector", "RateLimiter",
    "GracefulShutdown", "StructuredLogger", "ProductionStack",
    "get_production_stack",
]
