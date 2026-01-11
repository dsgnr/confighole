"""Configuration diffing utilities."""

from __future__ import annotations

from typing import Any


def calculate_lists_diff(
    local_lists: list[dict[str, Any]],
    remote_lists: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Calculate differences between local and remote Pi-hole lists.

    Compares lists by address and detects additions, removals, and changes
    to individual fields (type, comment, groups, enabled).

    Args:
        local_lists: List configurations from local YAML.
        remote_lists: List configurations from remote Pi-hole instance.

    Returns:
        Dictionary with 'add', 'change', and 'remove' keys containing
        the respective differences. Empty dict if no differences.
    """
    remote_lists = remote_lists or []

    # Create address-based lookups for O(1) access
    local_by_address = {item["address"]: item for item in local_lists}
    remote_by_address = {item["address"]: item for item in remote_lists}

    local_addresses = set(local_by_address.keys())
    remote_addresses = set(remote_by_address.keys())

    # Calculate differences using set operations
    to_add_addresses = local_addresses - remote_addresses
    to_remove_addresses = remote_addresses - local_addresses
    common_addresses = local_addresses & remote_addresses

    # Find items that need changes by comparing individual fields
    to_change: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for addr in common_addresses:
        local_item = local_by_address[addr]
        remote_item = remote_by_address[addr]

        if _list_items_differ(local_item, remote_item):
            to_change.append((local_item, remote_item))

    # Build result dictionary
    result: dict[str, dict[str, Any]] = {}

    if to_add_addresses:
        result["add"] = {"local": [local_by_address[addr] for addr in to_add_addresses]}

    if to_change:
        result["change"] = {
            "local": [local for local, _ in to_change],
            "remote": [remote for _, remote in to_change],
        }

    if to_remove_addresses:
        result["remove"] = {
            "remote": [remote_by_address[addr] for addr in to_remove_addresses]
        }

    return result


def _list_items_differ(local_item: dict[str, Any], remote_item: dict[str, Any]) -> bool:
    """Check if two list items have any differing fields.

    Args:
        local_item: Local list item configuration.
        remote_item: Remote list item configuration.

    Returns:
        True if any field differs, False otherwise.
    """
    fields_to_check = ["type", "comment", "groups", "enabled"]

    for field in fields_to_check:
        local_value = local_item.get(field)
        remote_value = remote_item.get(field)

        if field == "groups":
            # Normalise groups to sets for comparison (order doesn't matter)
            local_groups = _normalise_groups(local_value)
            remote_groups = _normalise_groups(remote_value)
            if local_groups != remote_groups:
                return True

        elif field == "enabled":
            # Normalise boolean values (default to True)
            local_enabled = bool(local_value) if local_value is not None else True
            remote_enabled = bool(remote_value) if remote_value is not None else True
            if local_enabled != remote_enabled:
                return True

        else:
            # Direct comparison for type and comment
            if local_value != remote_value:
                return True

    return False


def _normalise_groups(value: Any) -> frozenset[int]:
    """Normalise groups value to a frozenset for comparison.

    Args:
        value: Groups value (list, single int, or None).

    Returns:
        Frozenset of group IDs.
    """
    if isinstance(value, list):
        return frozenset(value)
    if value is not None:
        return frozenset([value])
    return frozenset([0])


def calculate_config_diff(
    local_config: Any,
    remote_config: Any,
    path: str = "",
) -> dict[str, dict[str, Any]]:
    """Recursively calculate differences between local and remote configurations.

    Only keys present in local configuration are considered for comparison.
    This allows partial configuration management where only specified keys
    are synchronised.

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
    """Convert nested structures to hashable types for comparison.

    Args:
        item: Value to convert (dict, list, or primitive).

    Returns:
        Hashable representation of the item.
    """
    if isinstance(item, dict):
        return frozenset((k, _make_hashable(v)) for k, v in item.items())
    if isinstance(item, list):
        return tuple(_make_hashable(x) for x in item)
    return item
