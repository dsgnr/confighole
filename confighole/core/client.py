"""Handles talking to the Pi-hole API - fetching and updating config."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Any, TypeVar

from pihole_lib.client import PiHoleClient
from pihole_lib.models.client_mgmt import ClientBatchDeleteItem
from pihole_lib.models.domains import DomainBatchDeleteItem, DomainKind, DomainType
from pihole_lib.models.lists import BatchDeleteItem, ListType

from confighole.utils.config import resolve_password, validate_instance_config
from confighole.utils.helpers import (
    normalise_configuration,
    normalise_remote_clients,
    normalise_remote_domains,
    normalise_remote_groups,
    normalise_remote_lists,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PiHoleManager:
    """Wraps the Pi-hole API client with a context manager interface.

    Use it like:
        with PiHoleManager("http://pihole.local", "password") as manager:
            config = manager.fetch_configuration()
    """

    def __init__(
        self,
        base_url: str,
        password: str,
        timeout: int = 30,
        verify_ssl: bool = True,
    ) -> None:
        """Set up the manager. Doesn't connect until you enter the context."""
        if not password:
            raise ValueError("Password cannot be None or empty")

        self.base_url = base_url
        self.password = password
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client: PiHoleClient | None = None

    def __enter__(self) -> PiHoleManager:
        """Connect to the Pi-hole."""
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
        """Clean up the connection."""
        if self._client:
            self._client.__exit__(exc_type, exc_val, exc_tb)

    def _handle_auth_error(self, exc: Exception) -> None:
        """Log a helpful message if it looks like an auth problem."""
        error_msg = str(exc).lower()
        if "credentials" in error_msg or "unauthorised" in error_msg:
            logger.error("Authentication failed - check your password configuration")

    def _ensure_client(self) -> PiHoleClient:
        """Get the client, raising if we're not connected yet."""
        if not self._client:
            raise RuntimeError("Client not initialised")
        return self._client

    def _fetch(
        self,
        label: str,
        call: Callable[[PiHoleClient], Any],
        normalise: Callable[[Any], T],
    ) -> T:
        """Fetch one resource type and normalise it, logging and re-raising on failure."""
        client = self._ensure_client()

        try:
            logger.debug("Fetching Pi-hole %s...", label)
            return normalise(call(client))

        except Exception as exc:
            logger.error("Failed to fetch %s: %s", label, exc)
            self._handle_auth_error(exc)
            raise

    def _apply(
        self,
        label: str,
        changes: dict[str, dict[str, Any]],
        steps: Sequence[Callable[[PiHoleClient, dict[str, dict[str, Any]]], None]],
    ) -> None:
        """Run the add, change and remove steps for one resource type."""
        client = self._ensure_client()

        if not changes:
            logger.info("No %s changes to apply", label)
            return

        for step in steps:
            step(client, changes)

        logger.info("Successfully applied %s changes", label)

    def fetch_configuration(self) -> dict[str, Any]:
        """Get the current Pi-hole config, normalised to our format."""
        return self._fetch(
            "configuration",
            lambda client: client.config.get_config(),
            normalise_configuration,
        )

    def fetch_lists(self) -> list[dict[str, Any]]:
        """Get all adlists from the Pi-hole."""
        return self._fetch(
            "lists",
            lambda client: client.lists.get_lists(),
            normalise_remote_lists,
        )

    def fetch_domains(self) -> list[dict[str, Any]]:
        """Get all domain entries (whitelist/blacklist) from the Pi-hole."""
        return self._fetch(
            "domains",
            lambda client: client.domains.get_domains(),
            normalise_remote_domains,
        )

    def fetch_groups(self) -> list[dict[str, Any]]:
        """Get all groups from the Pi-hole."""
        return self._fetch(
            "groups",
            lambda client: client.groups.get_groups(),
            normalise_remote_groups,
        )

    def fetch_clients(self) -> list[dict[str, Any]]:
        """Get all client definitions from the Pi-hole."""
        return self._fetch(
            "clients",
            lambda client: client.clients.get_clients(),
            normalise_remote_clients,
        )

    def update_gravity(self) -> bool:
        """Trigger a gravity update (re-download all adlists)."""
        client = self._ensure_client()

        try:
            logger.info("Updating gravity database...")
            for line in client.actions.update_gravity():
                logger.debug("Gravity: %s", line.strip())
            logger.info("Gravity update completed")
            return True

        except Exception as exc:
            logger.error("Failed to update gravity: %s", exc)
            return False

    def update_configuration(
        self,
        config_changes: dict[str, Any],
    ) -> None:
        """Push config changes to the Pi-hole. Raises on failure."""
        client = self._ensure_client()

        if not config_changes:
            logger.info("No configuration changes to apply")
            return

        client.config.update_config(config_changes)
        logger.info(
            "Successfully applied configuration changes: %s",
            list(config_changes.keys()),
        )

    def update_lists(
        self,
        lists_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply list changes (add/change/remove). Raises on failure."""
        self._apply(
            "list",
            lists_changes,
            (
                self._apply_list_additions,
                self._apply_list_changes,
                self._apply_list_removals,
            ),
        )

    def _apply_list_additions(
        self,
        client: PiHoleClient,
        lists_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Add new lists."""
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
        """Update existing lists (delete old version, add new)."""
        if "change" not in lists_changes:
            return

        items_to_delete = [
            BatchDeleteItem(item=item["address"], type=ListType(item["type"]))
            for item in lists_changes["change"]["remote"]
        ]

        if items_to_delete:
            client.lists.batch_delete_lists(items_to_delete)
            logger.debug(
                "Deleted old versions: %s", [item.item for item in items_to_delete]
            )

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
        """Remove lists that shouldn't exist."""
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
    ) -> None:
        """Apply domain changes (add/change/remove). Raises on failure."""
        self._apply(
            "domain",
            domains_changes,
            (
                self._apply_domain_additions,
                self._apply_domain_changes,
                self._apply_domain_removals,
            ),
        )

    def _apply_domain_additions(
        self,
        client: PiHoleClient,
        domains_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Add new domain entries."""
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
        """Update existing domains (delete old, add new)."""
        if "change" not in domains_changes:
            return

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
        """Remove domains that shouldn't exist."""
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
    ) -> None:
        """Apply group changes (add/change/remove). Raises on failure."""
        self._apply(
            "group",
            groups_changes,
            (
                self._apply_group_additions,
                self._apply_group_changes,
                self._apply_group_removals,
            ),
        )

    def _apply_group_additions(
        self,
        client: PiHoleClient,
        groups_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Create new groups."""
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
        """Update existing groups."""
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
        """Delete groups that shouldn't exist."""
        if "remove" not in groups_changes:
            return

        for group_item in groups_changes["remove"]["remote"]:
            client.groups.delete_group(group_item["name"])
            logger.debug("Removed group: %s", group_item["name"])

    def update_clients(
        self,
        clients_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply client changes (add/change/remove). Raises on failure."""
        self._apply(
            "client",
            clients_changes,
            (
                self._apply_client_additions,
                self._apply_client_changes,
                self._apply_client_removals,
            ),
        )

    def _apply_client_additions(
        self,
        client: PiHoleClient,
        clients_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Add new client definitions."""
        if "add" not in clients_changes:
            return

        for client_item in clients_changes["add"]["local"]:
            client.clients.add_client(
                client=client_item["client"],
                comment=client_item.get("comment"),
                groups=client_item.get("groups", [0]),
            )
            logger.debug("Added client: %s", client_item["client"])

    def _apply_client_changes(
        self,
        client: PiHoleClient,
        clients_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Update existing client definitions."""
        if "change" not in clients_changes:
            return

        for client_item in clients_changes["change"]["local"]:
            client.clients.update_client(
                client=client_item["client"],
                comment=client_item.get("comment"),
                groups=client_item.get("groups", [0]),
            )
            logger.debug("Updated client: %s", client_item["client"])

    def _apply_client_removals(
        self,
        client: PiHoleClient,
        clients_changes: dict[str, dict[str, Any]],
    ) -> None:
        """Remove client definitions that shouldn't exist."""
        if "remove" not in clients_changes:
            return

        items_to_remove = [
            ClientBatchDeleteItem(item=item["client"])
            for item in clients_changes["remove"]["remote"]
        ]

        if items_to_remove:
            client.clients.batch_delete_clients(items_to_remove)
            logger.debug("Removed clients: %s", [item.item for item in items_to_remove])


def create_manager(instance_config: dict[str, Any]) -> PiHoleManager:
    """Build a PiHoleManager from an instance config dict.

    Raises ConfigurationError if the base URL or password is missing.
    """
    validate_instance_config(instance_config)

    return PiHoleManager(
        base_url=instance_config["base_url"],
        password=resolve_password(instance_config) or "",
        timeout=instance_config.get("timeout", 30),
        verify_ssl=instance_config.get("verify_ssl", True),
    )
