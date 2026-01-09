"""Pi-hole client operations and data fetching."""

import logging
from typing import Any

from pihole_lib import PiHoleClient

from confighole.utils.config import (
    resolve_password,
    validate_instance_config,
)
from confighole.utils.exceptions import ConfigurationError
from confighole.utils.helpers import normalise_dns_configuration

logger = logging.getLogger(__name__)


class PiHoleManager:
    """Manages Pi-hole client operations and configuration synchronisation."""

    def __init__(
        self, base_url: str, password: str, timeout: int = 30, verify_ssl: bool = True
    ) -> None:
        """Initialise Pi-hole manager."""
        if not password:
            raise ValueError("Password cannot be None or empty")

        self.base_url = base_url
        self.password = password
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client: PiHoleClient | None = None

    def __enter__(self) -> "PiHoleManager":
        """Context manager entry."""
        logger.debug(f"Connecting to Pi-hole at {self.base_url}")

        try:
            self._client = PiHoleClient(
                self.base_url,
                password=self.password,
                timeout=self.timeout,
                verify_ssl=self.verify_ssl,
            )

            # Enter the client's context manager to authenticate
            self._client.__enter__()
            return self
        except Exception as exc:
            logger.error(f"Failed to create Pi-hole client: {exc}")
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        if self._client:
            self._client.__exit__(exc_type, exc_val, exc_tb)

    def fetch_configuration(self) -> dict[str, Any]:
        """Fetch and normalise remote Pi-hole configuration."""
        if not self._client:
            raise RuntimeError("Client not initialised")

        try:
            logger.debug("Fetching Pi-hole configuration...")
            raw_config = self._client.config.get_config()
            return normalise_dns_configuration(raw_config)
        except Exception as exc:
            logger.error(f"Failed to fetch configuration: {exc}")
            if "credentials" in str(exc).lower() or "unauthorised" in str(exc).lower():
                logger.error(
                    "Authentication failed - check your password configuration"
                )
            raise

    def update_configuration(
        self, config_changes: dict[str, Any], *, dry_run: bool = False
    ) -> bool:
        """Apply configuration changes to Pi-hole instance."""
        if not self._client:
            raise RuntimeError("Client not initialised")

        if not config_changes:
            logger.info("No configuration changes to apply")
            return True

        try:
            if dry_run:
                logger.info(
                    f"Would apply configuration changes: {list(config_changes.keys())}"
                )
                return True

            self._client.config.update_config(config_changes)
            logger.info(
                f"Successfully applied configuration changes: {list(config_changes.keys())}"
            )
            return True

        except Exception as exc:
            logger.error(f"Failed to update configuration: {exc}")
            return False


def create_manager(instance_config: dict[str, Any]) -> PiHoleManager | None:
    """Create a Pi-hole manager from instance configuration."""
    try:
        validate_instance_config(instance_config)

        base_url = instance_config.get("base_url")
        password = resolve_password(instance_config)
        timeout = instance_config.get("timeout", 30)
        verify_ssl = instance_config.get("verify_ssl", True)

        if not base_url or not password:
            return None

        return PiHoleManager(
            base_url=base_url, password=password, timeout=timeout, verify_ssl=verify_ssl
        )

    except (ConfigurationError, ValueError) as exc:
        logger.error(
            f"Configuration error for instance '{instance_config.get('name', 'unknown')}': {exc}"
        )
        return None
