"""High-level Pi-hole operations for different modes."""

import logging
from typing import Any

import yaml

from confighole.core.client import create_manager
from confighole.utils.diff import calculate_config_diff
from confighole.utils.exceptions import ConfigurationError
from confighole.utils.helpers import (
    convert_diff_to_nested_dict,
    normalise_dns_configuration,
)

logger = logging.getLogger(__name__)


def dump_instance_data(instance_config: dict[str, Any]) -> dict[str, Any] | None:
    """Dump configuration from a Pi-hole instance."""
    name = instance_config.get("name", "unknown")
    base_url = instance_config.get("base_url")
    manager = create_manager(instance_config)

    if not manager:
        return None

    logger.info(f"Connecting to {name} ({base_url})")

    try:
        with manager:
            return {
                "name": name,
                "base_url": base_url,
                "config": manager.fetch_configuration(),
            }
    except Exception as exc:
        logger.error(f"Failed to connect to '{name}': {exc}")
        return None


def diff_instance_config(instance_config: dict[str, Any]) -> dict[str, Any] | None:
    """Compare local configuration against remote Pi-hole instance."""
    name = instance_config.get("name", "unknown")
    local_config = instance_config.get("config")

    if not local_config:
        logger.warning(f"No local configuration found for instance '{name}'")
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info(f"Comparing configuration for {name}")

    try:
        with manager:
            remote_config = manager.fetch_configuration()
            normalised_local = normalise_dns_configuration(local_config)
            differences = calculate_config_diff(normalised_local, remote_config)

            if not differences:
                logger.info(f"No differences found for '{name}'")
                return None

            return {
                "name": name,
                "base_url": instance_config.get("base_url"),
                "diff": differences,
            }
    except Exception as exc:
        logger.error(f"Failed to compare configuration for '{name}': {exc}")
        return None


def sync_instance_config(
    instance_config: dict[str, Any], *, dry_run: bool = False
) -> dict[str, Any] | None:
    """Synchronise local configuration to Pi-hole instance."""
    name = instance_config.get("name", "unknown")
    local_config = instance_config.get("config")

    if not local_config:
        logger.info(f"No local configuration found for instance '{name}'")
        return None

    manager = create_manager(instance_config)
    if not manager:
        return None

    logger.info(f"Synchronising configuration for {name}")

    try:
        with manager:
            remote_config = manager.fetch_configuration()
            normalised_local = normalise_dns_configuration(local_config)
            changes = calculate_config_diff(normalised_local, remote_config)

            if not changes:
                logger.info(f"No changes required for '{name}'")
                return None

            if dry_run:
                logger.info(f"Would apply changes for '{name}':")
                print(yaml.dump(changes, sort_keys=False, default_flow_style=False))
            else:
                nested_changes = convert_diff_to_nested_dict(changes)
                if not manager.update_configuration(nested_changes, dry_run=False):
                    return None

            return {
                "name": name,
                "base_url": instance_config.get("base_url"),
                "changes": changes,
            }
    except Exception as exc:
        logger.error(f"Failed to synchronise configuration for '{name}': {exc}")
        return None


def process_instances(
    instances: list[dict[str, Any]], operation: str, **kwargs: Any
) -> list[dict[str, Any]]:
    """Process multiple Pi-hole instances with the specified operation."""
    operations = {
        "dump": dump_instance_data,
        "diff": diff_instance_config,
        "sync": lambda inst: sync_instance_config(
            inst, dry_run=kwargs.get("dry_run", False)
        ),
    }

    if operation not in operations:
        raise ValueError(f"Unknown operation: {operation}")

    operation_func = operations[operation]
    results = []

    for instance in instances:
        try:
            result = operation_func(instance)
            if result:
                results.append(result)
        except ConfigurationError as exc:
            logger.error(f"Configuration error: {exc}")
            continue

    return results
