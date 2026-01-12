"""Configuration diffing utilities."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _calculate_items_diff(
    local_items: list[dict[str, Any]],
    remote_items: list[dict[str, Any]] | None,
    key_func: Callable[[dict[str, Any]], Any],
    compare_fields: list[str],
) -> dict[str, dict[str, Any]]:
    """Calculate differences between local and remote item lists.

    Args:
        local_items: Items from local YAML.
        remote_items: Items from remote Pi-hole instance.
        key_func: Function to extract unique key from an item.
        compare_fields: Fields to compare for changes.

    Returns:
        Dictionary with 'add', 'change', and 'remove' keys.
    """
    remote_items = remote_items or []

    local_by_key = {key_func(item): item for item in local_items}
    remote_by_key = {key_func(item): item for item in remote_items}

    local_keys = set(local_by_key.keys())
    remote_keys = set(remote_by_key.keys())

    to_add_keys = local_keys - remote_keys
    to_remove_keys = remote_keys - local_keys
    common_keys = local_keys & remote_keys

    to_change: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for key in common_keys:
        local_item = local_by_key[key]
        remote_item = remote_by_key[key]
        if _items_differ(local_item, remote_item, compare_fields):
            to_change.append((local_item, remote_item))

    result: dict[str, dict[str, Any]] = {}

    if to_add_keys:
        result["add"] = {"local": [local_by_key[key] for key in to_add_keys]}

    if to_change:
        result["change"] = {
            "local": [local for local, _ in to_change],
            "remote": [remote for _, remote in to_change],
        }

    if to_remove_keys:
        result["remove"] = {"remote": [remote_by_key[key] for key in to_remove_keys]}

    return result


def _items_differ(
    local_item: dict[str, Any],
    remote_item: dict[str, Any],
    fields: list[str],
) -> bool:
    """Check if two items have any differing fields."""
    for field in fields:
        local_value = local_item.get(field)
        remote_value = remote_item.get(field)

        if field == "groups":
            if _normalise_groups(local_value) != _normalise_groups(remote_value):
                return True
        elif field == "enabled":
            local_enabled = bool(local_value) if local_value is not None else True
            remote_enabled = bool(remote_value) if remote_value is not None else True
            if local_enabled != remote_enabled:
                return True
        elif local_value != remote_value:
            return True

    return False


def _normalise_groups(value: Any) -> frozenset[int]:
    """Normalise groups value to a frozenset for comparison."""
    if isinstance(value, list):
        return frozenset(value)
    if value is not None:
        return frozenset([value])
    return frozenset([0])


def calculate_lists_diff(
    local_lists: list[dict[str, Any]],
    remote_lists: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Calculate differences between local and remote Pi-hole lists.

    Compares lists by address and detects additions, removals, and changes.

    Args:
        local_lists: List configurations from local YAML.
        remote_lists: List configurations from remote Pi-hole instance.

    Returns:
        Dictionary with 'add', 'change', and 'remove' keys.
    """
    return _calculate_items_diff(
        local_lists,
        remote_lists,
        key_func=lambda item: item["address"],
        compare_fields=["type", "comment", "groups", "enabled"],
    )


def calculate_domains_diff(
    local_domains: list[dict[str, Any]],
    remote_domains: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Calculate differences between local and remote Pi-hole domains.

    Compares domains by (domain, type, kind) composite key.

    Args:
        local_domains: Domain configurations from local YAML.
        remote_domains: Domain configurations from remote Pi-hole instance.

    Returns:
        Dictionary with 'add', 'change', and 'remove' keys.
    """
    return _calculate_items_diff(
        local_domains,
        remote_domains,
        key_func=lambda item: (item["domain"], item["type"], item["kind"]),
        compare_fields=["comment", "groups", "enabled"],
    )


def calculate_groups_diff(
    local_groups: list[dict[str, Any]],
    remote_groups: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Calculate differences between local and remote Pi-hole groups.

    Compares groups by name.

    Args:
        local_groups: Group configurations from local YAML.
        remote_groups: Group configurations from remote Pi-hole instance.

    Returns:
        Dictionary with 'add', 'change', and 'remove' keys.
    """
    return _calculate_items_diff(
        local_groups,
        remote_groups,
        key_func=lambda item: item["name"],
        compare_fields=["comment", "enabled"],
    )


def calculate_clients_diff(
    local_clients: list[dict[str, Any]],
    remote_clients: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Calculate differences between local and remote Pi-hole clients.

    Compares clients by client identifier.

    Args:
        local_clients: Client configurations from local YAML.
        remote_clients: Client configurations from remote Pi-hole instance.

    Returns:
        Dictionary with 'add', 'change', and 'remove' keys.
    """
    return _calculate_items_diff(
        local_clients,
        remote_clients,
        key_func=lambda item: item["client"],
        compare_fields=["comment", "groups"],
    )


def calculate_config_diff(
    local_config: Any,
    remote_config: Any,
    path: str = "",
) -> dict[str, dict[str, Any]]:
    """Recursively calculate differences between local and remote configurations.

    Only keys present in local configuration are considered for comparison.

    Args:
        local_config: Local configuration (source of truth).
        remote_config: Remote configuration from Pi-hole.
        path: Current path in the configuration tree (for nested keys).

    Returns:
        Dictionary mapping dotted paths to {'local': ..., 'remote': ...} diffs.
    """
    differences: dict[str, dict[str, Any]] = {}

    if remote_config is None:
        remote_config = (
            type(local_config)() if isinstance(local_config, dict | list) else None
        )

    if type(local_config) is not type(remote_config):
        return {path: {"local": local_config, "remote": remote_config}}

    match local_config:
        case dict():
            for key, value in local_config.items():
                new_path = f"{path}.{key}" if path else key
                differences |= calculate_config_diff(
                    value, remote_config.get(key), new_path
                )

        case list():
            local_set = {_make_hashable(x) for x in local_config}
            remote_set = {_make_hashable(x) for x in remote_config or []}

            if local_set != remote_set:
                differences[path] = {"local": local_config, "remote": remote_config}

        case _:
            if local_config != remote_config:
                differences[path] = {"local": local_config, "remote": remote_config}

    return differences


def _make_hashable(item: Any) -> Any:
    """Convert nested structures to hashable types for comparison."""
    if isinstance(item, dict):
        return frozenset((k, _make_hashable(v)) for k, v in item.items())
    if isinstance(item, list):
        return tuple(_make_hashable(x) for x in item)
    return item
