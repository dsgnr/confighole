"""High-level Pi-hole operations for different modes."""

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
    """Dump configuration from a Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.

    Returns:
        Dictionary containing instance name, URL, config, and lists.
        None if connection fails.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Connecting to for %s (%s)", name, base_url)

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
        logger.error("Failed to connect to for '%s': %s", name, exc)
        return None


def diff_instance_config(instance_config: dict[str, Any]) -> dict[str, Any] | None:
    """Compare local configuration against remote Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.

    Returns:
        Dictionary containing differences, or None if no differences.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    local_config = instance_config.get("config")
    local_lists = instance_config.get("lists")
    local_domains = instance_config.get("domains")
    local_groups = instance_config.get("groups")
    local_clients = instance_config.get("clients")

    # Check if any local configuration exists
    has_local_config = any(
        [local_config, local_lists, local_domains, local_groups, local_clients]
    )
    if not has_local_config:
        logger.info("No local configuration found for instance '%s'", name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Comparing configuration for %s (%s)", name, base_url)

    try:
        with manager:
            differences: dict[str, Any] = {}

            if local_config:
                remote_config = manager.fetch_configuration()
                normalised_local_config = normalise_configuration(local_config)
                config_diff = calculate_config_diff(
                    normalised_local_config, remote_config
                )
                if config_diff:
                    differences["config"] = config_diff

            if local_lists is not None:
                remote_lists = manager.fetch_lists()
                lists_diff = calculate_lists_diff(local_lists, remote_lists)
                if lists_diff:
                    differences["lists"] = lists_diff

            if local_domains is not None:
                remote_domains = manager.fetch_domains()
                domains_diff = calculate_domains_diff(local_domains, remote_domains)
                if domains_diff:
                    differences["domains"] = domains_diff

            if local_groups is not None:
                remote_groups = manager.fetch_groups()
                groups_diff = calculate_groups_diff(local_groups, remote_groups)
                if groups_diff:
                    differences["groups"] = groups_diff

            if local_clients is not None:
                remote_clients = manager.fetch_clients()
                clients_diff = calculate_clients_diff(local_clients, remote_clients)
                if clients_diff:
                    differences["clients"] = clients_diff

            if not differences:
                logger.info("No differences found for '%s'", name)
                return None

            return {
                "name": name,
                "base_url": base_url,
                "diff": differences,
            }

    except Exception as exc:
        logger.error("Failed to compare configuration for '%s': %s", name, exc)
        return None


def sync_instance_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Synchronise local configuration to Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.
        dry_run: If True, only report what would change without applying.

    Returns:
        Dictionary containing applied changes, or None if no changes needed.
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

            return {
                "name": name,
                "base_url": base_url,
                "changes": changes,
            }

    except Exception as exc:
        logger.error("Failed to synchronise configuration for '%s': %s", name, exc)
        return None


def sync_list_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Synchronise local lists configuration to Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.
        dry_run: If True, only report what would change without applying.

    Returns:
        Dictionary containing applied changes, or None if no changes needed.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    local_lists = instance_config.get("lists")
    update_gravity = instance_config.get("update_gravity", False)

    if not local_lists:
        logger.info("No local lists found for instance '%s'", name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Synchronising lists for '%s' (%s)", name, base_url)

    try:
        with manager:
            remote_lists = manager.fetch_lists()
            changes = calculate_lists_diff(local_lists, remote_lists)

            if not changes:
                logger.info("No list changes required for '%s'", name)
                return None

            if dry_run:
                logger.info("Would apply list changes for '%s':", name)
                print(yaml.dump(changes, sort_keys=False, default_flow_style=False))
                if update_gravity:
                    logger.info("Would update gravity for '%s'", name)
            else:
                if not manager.update_lists(changes, dry_run=False):
                    return None

                if update_gravity:
                    manager.update_gravity()

            return {
                "name": name,
                "base_url": base_url,
                "changes": changes,
            }

    except Exception as exc:
        logger.error("Failed to synchronise lists for '%s': %s", name, exc)
        return None


def sync_domain_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Synchronise local domains configuration to Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.
        dry_run: If True, only report what would change without applying.

    Returns:
        Dictionary containing applied changes, or None if no changes needed.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    local_domains = instance_config.get("domains")

    if not local_domains:
        logger.info("No local domains found for instance '%s'", name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Synchronising domains for '%s' (%s)", name, base_url)

    try:
        with manager:
            remote_domains = manager.fetch_domains()
            changes = calculate_domains_diff(local_domains, remote_domains)

            if not changes:
                logger.info("No domain changes required for '%s'", name)
                return None

            if dry_run:
                logger.info("Would apply domain changes for '%s':", name)
                print(yaml.dump(changes, sort_keys=False, default_flow_style=False))
            else:
                if not manager.update_domains(changes, dry_run=False):
                    return None

            return {
                "name": name,
                "base_url": base_url,
                "changes": changes,
            }

    except Exception as exc:
        logger.error("Failed to synchronise domains for '%s': %s", name, exc)
        return None


def sync_group_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Synchronise local groups configuration to Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.
        dry_run: If True, only report what would change without applying.

    Returns:
        Dictionary containing applied changes, or None if no changes needed.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    local_groups = instance_config.get("groups")

    if not local_groups:
        logger.info("No local groups found for instance '%s'", name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Synchronising groups for '%s' (%s)", name, base_url)

    try:
        with manager:
            remote_groups = manager.fetch_groups()
            changes = calculate_groups_diff(local_groups, remote_groups)

            if not changes:
                logger.info("No group changes required for '%s'", name)
                return None

            if dry_run:
                logger.info("Would apply group changes for '%s':", name)
                print(yaml.dump(changes, sort_keys=False, default_flow_style=False))
            else:
                if not manager.update_groups(changes, dry_run=False):
                    return None

            return {
                "name": name,
                "base_url": base_url,
                "changes": changes,
            }

    except Exception as exc:
        logger.error("Failed to synchronise groups for '%s': %s", name, exc)
        return None


def sync_client_config(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Synchronise local clients configuration to Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.
        dry_run: If True, only report what would change without applying.

    Returns:
        Dictionary containing applied changes, or None if no changes needed.
    """
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    local_clients = instance_config.get("clients")

    if not local_clients:
        logger.info("No local clients found for instance '%s'", name)
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info("Synchronising clients for '%s' (%s)", name, base_url)

    try:
        with manager:
            remote_clients = manager.fetch_clients()
            changes = calculate_clients_diff(local_clients, remote_clients)

            if not changes:
                logger.info("No client changes required for '%s'", name)
                return None

            if dry_run:
                logger.info("Would apply client changes for '%s':", name)
                print(yaml.dump(changes, sort_keys=False, default_flow_style=False))
            else:
                if not manager.update_clients(changes, dry_run=False):
                    return None

            return {
                "name": name,
                "base_url": base_url,
                "changes": changes,
            }

    except Exception as exc:
        logger.error("Failed to synchronise clients for '%s': %s", name, exc)
        return None


def sync(
    instance_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Synchronise all configuration to Pi-hole instance.

    Args:
        instance_config: Instance configuration dictionary.
        dry_run: If True, only report what would change without applying.

    Returns:
        Dictionary containing applied changes, or None if no changes needed.
    """
    name = instance_config.get("name", "unknown")
    results: dict[str, Any] = {}

    config_result = sync_instance_config(instance_config, dry_run=dry_run)
    if config_result:
        results["config"] = config_result.get("changes", {})

    lists_result = sync_list_config(instance_config, dry_run=dry_run)
    if lists_result:
        results["lists"] = lists_result.get("changes", {})

    domains_result = sync_domain_config(instance_config, dry_run=dry_run)
    if domains_result:
        results["domains"] = domains_result.get("changes", {})

    groups_result = sync_group_config(instance_config, dry_run=dry_run)
    if groups_result:
        results["groups"] = groups_result.get("changes", {})

    clients_result = sync_client_config(instance_config, dry_run=dry_run)
    if clients_result:
        results["clients"] = clients_result.get("changes", {})

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
    """Process multiple Pi-hole instances with the specified operation.

    Args:
        instances: List of instance configuration dictionaries.
        operation: Operation name ('dump', 'diff', or 'sync').
        **kwargs: Additional arguments passed to the operation (e.g. dry_run).

    Returns:
        List of results from each successful operation.

    Raises:
        ValueError: If operation is not recognised.
    """
    dry_run = kwargs.get("dry_run", False)

    if operation not in ("dump", "diff", "sync"):
        raise ValueError(f"Unknown operation: {operation}")

    results: list[dict[str, Any]] = []

    for instance in instances:
        try:
            if operation == "dump":
                result = dump_instance_data(instance)
            elif operation == "diff":
                result = diff_instance_config(instance)
            else:
                result = sync(instance, dry_run=dry_run)

            if result:
                results.append(result)

        except ConfigurationError as exc:
            logger.error("Configuration error: %s", exc)

    return results
