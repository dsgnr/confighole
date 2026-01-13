"""High-level operations for dumping, diffing, and syncing Pi-hole configs."""

from __future__ import annotations

import logging
from typing import Any

import yaml

from confighole.core.client import create_manager
from confighole.utils.diff import (
    calculate_clients_diff,
    calculate_config_diff,
    calculate_domains_diff,
    calculate_groups_diff,
    calculate_lists_diff,
)
from confighole.utils.exceptions import ConfigurationError
from confighole.utils.helpers import (
    convert_diff_to_nested_dict,
    normalise_configuration,
)

logger = logging.getLogger(__name__)


def dump_instance_data(instance_config: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch everything from a Pi-hole instance and return it as a dict.

    Returns None if we can't connect.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Connecting to %s (%s)", name, base_url)

    try:
        with manager:
            return {
                "name": name,
                "base_url": base_url,
                "config": manager.fetch_configuration(),
                "lists": manager.fetch_lists(),
                "domains": manager.fetch_domains(),
                "groups": manager.fetch_groups(),
                "clients": manager.fetch_clients(),
            }
    except Exception as exc:
        logger.error("Failed to connect to '%s': %s", name, exc)
        return None


def diff_instance_config(instance_config: dict[str, Any]) -> dict[str, Any] | None:
    """Compare local config against what's on the Pi-hole.

    Returns None if there are no differences or we can't connect.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")

    # Extract local configurations
    local_config = instance_config.get("config")
    local_lists = instance_config.get("lists")
    local_domains = instance_config.get("domains")
    local_groups = instance_config.get("groups")
    local_clients = instance_config.get("clients")

    # Check if any local configuration exists
    if not any([local_config, local_lists, local_domains, local_groups, local_clients]):
        logger.info("No local configuration found for instance '%s'", name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Comparing configuration for %s (%s)", name, base_url)

    try:
        with manager:
            differences: dict[str, Any] = {}

            # Compare each configuration type
            diff_specs = [
                (
                    local_config,
                    manager.fetch_configuration,
                    "config",
                    lambda loc, rem: calculate_config_diff(
                        normalise_configuration(loc), rem
                    ),
                ),
                (local_lists, manager.fetch_lists, "lists", calculate_lists_diff),
                (
                    local_domains,
                    manager.fetch_domains,
                    "domains",
                    calculate_domains_diff,
                ),
                (local_groups, manager.fetch_groups, "groups", calculate_groups_diff),
                (
                    local_clients,
                    manager.fetch_clients,
                    "clients",
                    calculate_clients_diff,
                ),
            ]

            for local_data, fetch_func, key, diff_func in diff_specs:
                if local_data is not None:
                    remote_data = fetch_func()
                    diff = diff_func(local_data, remote_data)
                    if diff:
                        differences[key] = diff

            if not differences:
                logger.info("No differences found for '%s'", name)
                return None

            return {"name": name, "base_url": base_url, "diff": differences}

    except Exception as exc:
        logger.error("Failed to compare configuration for '%s': %s", name, exc)
        return None


def sync_instance_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Push local config settings to the Pi-hole.

    With dry_run=True, just shows what would change without doing it.
    Returns None if there's nothing to sync or it fails.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    local_config = instance_config.get("config")

    if not local_config:
        logger.info("No local configuration found for instance '%s'", name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Synchronising configuration for %s (%s)", name, base_url)

    try:
        with manager:
            remote_config = manager.fetch_configuration()
            normalised_local = normalise_configuration(local_config)
            changes = calculate_config_diff(normalised_local, remote_config)

            if not changes:
                logger.info("No changes required for '%s'", name)
                return None

            if dry_run:
                logger.info("Would apply changes for '%s':", name)
                print(yaml.dump(changes, sort_keys=False, default_flow_style=False))
            else:
                nested_changes = convert_diff_to_nested_dict(changes)
                if not manager.update_configuration(nested_changes, dry_run=False):
                    return None

            return {"name": name, "base_url": base_url, "changes": changes}

    except Exception as exc:
        logger.error("Failed to synchronise configuration for '%s': %s", name, exc)
        return None


def _sync_resource(
    instance_config: dict[str, Any],
    resource_key: str,
    fetch_method: str,
    update_method: str,
    diff_func: Any,
    *,
    dry_run: bool = False,
    post_sync_action: str | None = None,
) -> dict[str, Any] | None:
    """Shared logic for syncing lists, domains, groups, or clients."""
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    local_data = instance_config.get(resource_key)

    if not local_data:
        logger.info("No local %s found for instance '%s'", resource_key, name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Synchronising %s for '%s' (%s)", resource_key, name, base_url)

    try:
        with manager:
            remote_data = getattr(manager, fetch_method)()
            changes = diff_func(local_data, remote_data)

            if not changes:
                logger.info("No %s changes required for '%s'", resource_key, name)
                return None

            if dry_run:
                logger.info("Would apply %s changes for '%s':", resource_key, name)
                print(yaml.dump(changes, sort_keys=False, default_flow_style=False))
                if post_sync_action and instance_config.get("update_gravity"):
                    logger.info("Would %s for '%s'", post_sync_action, name)
            else:
                if not getattr(manager, update_method)(changes, dry_run=False):
                    return None
                if post_sync_action and instance_config.get("update_gravity"):
                    getattr(manager, post_sync_action)()

            return {"name": name, "base_url": base_url, "changes": changes}

    except Exception as exc:
        logger.error("Failed to synchronise %s for '%s': %s", resource_key, name, exc)
        return None


def sync_list_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Sync adlists to the Pi-hole. Optionally triggers gravity update."""
    return _sync_resource(
        instance_config,
        resource_key="lists",
        fetch_method="fetch_lists",
        update_method="update_lists",
        diff_func=calculate_lists_diff,
        dry_run=dry_run,
        post_sync_action="update_gravity",
    )


def sync_domain_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Sync domain whitelist/blacklist entries to the Pi-hole."""
    return _sync_resource(
        instance_config,
        resource_key="domains",
        fetch_method="fetch_domains",
        update_method="update_domains",
        diff_func=calculate_domains_diff,
        dry_run=dry_run,
    )


def sync_group_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Sync groups to the Pi-hole."""
    return _sync_resource(
        instance_config,
        resource_key="groups",
        fetch_method="fetch_groups",
        update_method="update_groups",
        diff_func=calculate_groups_diff,
        dry_run=dry_run,
    )


def sync_client_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Sync client definitions to the Pi-hole."""
    return _sync_resource(
        instance_config,
        resource_key="clients",
        fetch_method="fetch_clients",
        update_method="update_clients",
        diff_func=calculate_clients_diff,
        dry_run=dry_run,
    )


def sync(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Sync everything (config, lists, domains, groups, clients) to the Pi-hole.

    Returns None if nothing needed syncing.
    """
    name = instance_config.get("name", "unknown")
    results: dict[str, Any] = {}

    # Define sync operations with their result keys
    sync_operations = [
        (sync_instance_config, "config"),
        (sync_list_config, "lists"),
        (sync_domain_config, "domains"),
        (sync_group_config, "groups"),
        (sync_client_config, "clients"),
    ]

    for sync_func, key in sync_operations:
        if result := sync_func(instance_config, dry_run=dry_run):
            results[key] = result.get("changes", {})

    if results:
        return {
            "name": name,
            "base_url": instance_config.get("base_url"),
            "changes": results,
        }

    logger.info("No configuration changes required for '%s'", name)
    return None


def process_instances(
    instances: list[dict[str, Any]],
    operation: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Run an operation (dump, diff, or sync) across multiple instances.

    Returns a list of results from instances that had something to report.
    """
    operations = {
        "dump": lambda inst, **kw: dump_instance_data(inst),
        "diff": lambda inst, **kw: diff_instance_config(inst),
        "sync": lambda inst, **kw: sync(inst, dry_run=kw.get("dry_run", False)),
    }

    if operation not in operations:
        raise ValueError(f"Unknown operation: {operation}")

    results: list[dict[str, Any]] = []
    op_func = operations[operation]

    for instance in instances:
        try:
            if result := op_func(instance, **kwargs):
                results.append(result)
        except ConfigurationError as exc:
            logger.error("Configuration error: %s", exc)

    return results
