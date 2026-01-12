"""Pi-hole client operations and data fetching."""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

from pihole_lib import PiHoleClient
from pihole_lib.models import (
    BatchDeleteItem,
    DomainBatchDeleteItem,
    DomainKind,
    DomainType,
    ListType,
)

from confighole.utils.config import resolve_password, validate_instance_config
from confighole.utils.exceptions import ConfigurationError
from confighole.utils.helpers import (
    normalise_configuration,
    normalise_remote_domains,
    normalise_remote_groups,
    normalise_remote_lists,
)

logger = logging.getLogger(__name__)


class PiHoleManager:
    """Manages Pi-hole client operations and configuration synchronisation.

    This class provides a context manager interface for connecting to a Pi-hole
    instance and performing configuration operations.

    Example:
        manager = PiHoleManager("http://pihole.local", "password")
        with manager:
            config = manager.fetch_configuration()
    """

    def __init__(
        self,
        base_url: str,
        password: str,
        timeout: int = 30,
        verify_ssl: bool = True,
    ) -> None:
        """Initialise Pi-hole manager.

        Args:
            base_url: Base URL of the Pi-hole instance.
            password: Authentication password.
            timeout: Request timeout in seconds.
            verify_ssl: Whether to verify SSL certificates.

        Raises:
            ValueError: If password is empty or None.
        """
        if not password:
            raise ValueError("Password cannot be None or empty")

        self.base_url = base_url
        self.password = password
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client: PiHoleClient | None = None

    def __enter__(self) -> PiHoleManager:
        """Context manager entry - establishes connection."""
        logger.debug("Connecting to Pi-hole at %s", self.base_url)

        try:
            self._client = PiHoleClient(
                self.base_url,
                password=self.password,
                timeout=self.timeout,
                verify_ssl=self.verify_ssl,
            )
            self._client.__enter__()
            return self

        except Exception as exc:
            logger.error("Failed to create Pi-hole client: %s", exc)
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit - cleans up connection."""
        if self._client:
            self._client.__exit__(exc_type, exc_val, exc_tb)

    def _handle_auth_error(self, exc: Exception) -> None:
        """Handle authentication-related errors."""
        error_msg = str(exc).lower()
        if "credentials" in error_msg or "unauthorised" in error_msg:
            logger.error("Authentication failed - check your password configuration")

    def _ensure_client(self) -> PiHoleClient:
        """Ensure client is initialised and return it.

        Returns:
            The initialised PiHoleClient.

        Raises:
            RuntimeError: If client is not initialised.
        """
        if not self._client:
            raise RuntimeError("Client not initialised")
        return self._client

    def fetch_configuration(self) -> dict[str, Any]:
        """Fetch and normalise remote Pi-hole configuration.

        Returns:
            Normalised configuration dictionary.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        try:
            logger.debug("Fetching Pi-hole configuration...")
            raw_config = client.config.get_config()
            return normalise_configuration(raw_config)

        except Exception as exc:
            logger.error("Failed to fetch configuration: %s", exc)
            self._handle_auth_error(exc)
            raise

    def fetch_lists(self) -> list[dict[str, Any]]:
        """Fetch remote Pi-hole lists.

        Returns:
            List of normalised list dictionaries.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        try:
            logger.debug("Fetching Pi-hole lists...")
            raw_lists = client.lists.get_lists()
            return normalise_remote_lists(raw_lists)

        except Exception as exc:
            logger.error("Failed to fetch lists: %s", exc)
            self._handle_auth_error(exc)
            raise

    def fetch_domains(self) -> list[dict[str, Any]]:
        """Fetch remote Pi-hole domains.

        Returns:
            List of normalised domain dictionaries.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        try:
            logger.debug("Fetching Pi-hole domains...")
            raw_domains = client.domains.get_domains()
            return normalise_remote_domains(raw_domains)

        except Exception as exc:
            logger.error("Failed to fetch domains: %s", exc)
            self._handle_auth_error(exc)
            raise

    def fetch_groups(self) -> list[dict[str, Any]]:
        """Fetch remote Pi-hole groups.

        Returns:
            List of normalised group dictionaries.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        try:
            logger.debug("Fetching Pi-hole groups...")
            raw_groups = client.groups.get_groups().groups
            return normalise_remote_groups(raw_groups)

        except Exception as exc:
            logger.error("Failed to fetch groups: %s", exc)
            self._handle_auth_error(exc)
            raise

    def update_configuration(
        self,
        config_changes: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> bool:
        """Apply configuration changes to Pi-hole instance.

        Args:
            config_changes: Nested dictionary of configuration changes.
            dry_run: If True, only log what would change without applying.

        Returns:
            True if successful, False on failure.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        if not config_changes:
            logger.info("No configuration changes to apply")
            return True

        try:
            if dry_run:
                logger.info(
                    "Would apply configuration changes: %s", list(config_changes.keys())
                )
                return True

            client.config.update_config(config_changes)
            logger.info(
                "Successfully applied configuration changes: %s",
                list(config_changes.keys()),
            )
            return True

        except Exception as exc:
            logger.error("Failed to update configuration: %s", exc)
            return False

    def update_lists(
        self,
        lists_changes: dict[str, dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> bool:
        """Apply list changes to Pi-hole instance.

        Args:
            lists_changes: Dictionary with 'add', 'change', and 'remove' keys.
            dry_run: If True, only log what would change without applying.

        Returns:
            True if successful, False on failure.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        if not lists_changes:
            logger.info("No list changes to apply")
            return True

        try:
            if dry_run:
                logger.info("Would apply list changes: %s", list(lists_changes.keys()))
                return True

            self._apply_list_additions(client, lists_changes)
            self._apply_list_changes(client, lists_changes)
            self._apply_list_removals(client, lists_changes)

            logger.info("Successfully applied list changes")
            return True

        except Exception as exc:
            logger.error("Failed to update lists: %s", exc)
            return False

    def _apply_list_additions(
        self,
        client: PiHoleClient,
        lists_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply list additions."""
        if "add" not in lists_changes:
            return

        for list_item in lists_changes["add"]["local"]:
            client.lists.add_list(
                address=list_item["address"],
                list_type=ListType(list_item["type"]),
                comment=list_item.get("comment", ""),
                groups=list_item.get("groups", [0]),
                enabled=list_item.get("enabled", True),
            )
            logger.debug("Added list: %s", list_item["address"])

    def _apply_list_changes(
        self,
        client: PiHoleClient,
        lists_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply list changes (delete old, add new)."""
        if "change" not in lists_changes:
            return

        # Delete old versions first
        items_to_delete = [
            BatchDeleteItem(item=item["address"], type=ListType(item["type"]))
            for item in lists_changes["change"]["remote"]
        ]

        if items_to_delete:
            client.lists.batch_delete_lists(items_to_delete)
            logger.debug(
                "Deleted old versions: %s", [item.item for item in items_to_delete]
            )

        # Add updated versions
        for list_item in lists_changes["change"]["local"]:
            client.lists.update_list(
                address=list_item["address"],
                list_type=ListType(list_item["type"]),
                comment=list_item.get("comment"),
                groups=list_item.get("groups"),
                enabled=list_item.get("enabled"),
            )
            logger.debug("Added updated list: %s", list_item["address"])

    def _apply_list_removals(
        self,
        client: PiHoleClient,
        lists_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply list removals."""
        if "remove" not in lists_changes:
            return

        items_to_remove = [
            BatchDeleteItem(item=item["address"], type=ListType(item["type"]))
            for item in lists_changes["remove"]["remote"]
        ]

        if items_to_remove:
            client.lists.batch_delete_lists(items_to_remove)
            logger.debug("Removed lists: %s", [item.item for item in items_to_remove])

    def update_domains(
        self,
        domains_changes: dict[str, dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> bool:
        """Apply domain changes to Pi-hole instance.

        Args:
            domains_changes: Dictionary with 'add', 'change', and 'remove' keys.
            dry_run: If True, only log what would change without applying.

        Returns:
            True if successful, False on failure.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        if not domains_changes:
            logger.info("No domain changes to apply")
            return True

        try:
            if dry_run:
                logger.info(
                    "Would apply domain changes: %s", list(domains_changes.keys())
                )
                return True

            self._apply_domain_additions(client, domains_changes)
            self._apply_domain_changes(client, domains_changes)
            self._apply_domain_removals(client, domains_changes)

            logger.info("Successfully applied domain changes")
            return True

        except Exception as exc:
            logger.error("Failed to update domains: %s", exc)
            return False

    def _apply_domain_additions(
        self,
        client: PiHoleClient,
        domains_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply domain additions."""
        if "add" not in domains_changes:
            return

        for domain_item in domains_changes["add"]["local"]:
            client.domains.add_domain(
                domain=domain_item["domain"],
                domain_type=DomainType(domain_item["type"]),
                domain_kind=DomainKind(domain_item["kind"]),
                comment=domain_item.get("comment", ""),
                groups=domain_item.get("groups", [0]),
                enabled=domain_item.get("enabled", True),
            )
            logger.debug("Added domain: %s", domain_item["domain"])

    def _apply_domain_changes(
        self,
        client: PiHoleClient,
        domains_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply domain changes (delete old, add new)."""
        if "change" not in domains_changes:
            return

        # Delete old versions first
        items_to_delete = [
            DomainBatchDeleteItem(
                item=item["domain"],
                type=DomainType(item["type"]),
                kind=DomainKind(item["kind"]),
            )
            for item in domains_changes["change"]["remote"]
        ]

        if items_to_delete:
            client.domains.batch_delete_domains(items_to_delete)
            logger.debug(
                "Deleted old domain versions: %s",
                [item.item for item in items_to_delete],
            )

        # Add updated versions
        for domain_item in domains_changes["change"]["local"]:
            client.domains.update_domain(
                domain=domain_item["domain"],
                domain_type=DomainType(domain_item["type"]),
                domain_kind=DomainKind(domain_item["kind"]),
                comment=domain_item.get("comment"),
                groups=domain_item.get("groups"),
                enabled=domain_item.get("enabled"),
            )
            logger.debug("Updated domain: %s", domain_item["domain"])

    def _apply_domain_removals(
        self,
        client: PiHoleClient,
        domains_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply domain removals."""
        if "remove" not in domains_changes:
            return

        items_to_remove = [
            DomainBatchDeleteItem(
                item=item["domain"],
                type=DomainType(item["type"]),
                kind=DomainKind(item["kind"]),
            )
            for item in domains_changes["remove"]["remote"]
        ]

        if items_to_remove:
            client.domains.batch_delete_domains(items_to_remove)
            logger.debug("Removed domains: %s", [item.item for item in items_to_remove])

    def update_groups(
        self,
        groups_changes: dict[str, dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> bool:
        """Apply group changes to Pi-hole instance.

        Args:
            groups_changes: Dictionary with 'add', 'change', and 'remove' keys.
            dry_run: If True, only log what would change without applying.

        Returns:
            True if successful, False on failure.

        Raises:
            RuntimeError: If client is not initialised.
        """
        client = self._ensure_client()

        if not groups_changes:
            logger.info("No group changes to apply")
            return True

        try:
            if dry_run:
                logger.info(
                    "Would apply group changes: %s", list(groups_changes.keys())
                )
                return True

            self._apply_group_additions(client, groups_changes)
            self._apply_group_changes(client, groups_changes)
            self._apply_group_removals(client, groups_changes)

            logger.info("Successfully applied group changes")
            return True

        except Exception as exc:
            logger.error("Failed to update groups: %s", exc)
            return False

    def _apply_group_additions(
        self,
        client: PiHoleClient,
        groups_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply group additions."""
        if "add" not in groups_changes:
            return

        for group_item in groups_changes["add"]["local"]:
            client.groups.create_group(
                name=group_item["name"],
                comment=group_item.get("comment"),
                enabled=group_item.get("enabled", True),
            )
            logger.debug("Added group: %s", group_item["name"])

    def _apply_group_changes(
        self,
        client: PiHoleClient,
        groups_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply group changes."""
        if "change" not in groups_changes:
            return

        for group_item in groups_changes["change"]["local"]:
            client.groups.update_group(
                name=group_item["name"],
                comment=group_item.get("comment"),
                enabled=group_item.get("enabled", True),
            )
            logger.debug("Updated group: %s", group_item["name"])

    def _apply_group_removals(
        self,
        client: PiHoleClient,
        groups_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply group removals."""
        if "remove" not in groups_changes:
            return

        for group_item in groups_changes["remove"]["remote"]:
            client.groups.delete_group(group_item["name"])
            logger.debug("Removed group: %s", group_item["name"])


def create_manager(instance_config: dict[str, Any]) -> PiHoleManager | None:
    """Create a Pi-hole manager from instance configuration.

    Args:
        instance_config: Instance configuration dictionary.

    Returns:
        Configured PiHoleManager, or None if configuration is invalid.
    """
    try:
        validate_instance_config(instance_config)

        base_url = instance_config.get("base_url")
        password = resolve_password(instance_config)
        timeout = instance_config.get("timeout", 30)
        verify_ssl = instance_config.get("verify_ssl", True)

        if not base_url or not password:
            return None

        return PiHoleManager(
            base_url=base_url,
            password=password,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

    except (ConfigurationError, ValueError) as exc:
        logger.error(
            "Configuration error for instance '%s': %s",
            instance_config.get("name", "unknown"),
            exc,
        )
        return None
