"""Configuration diffing utilities."""

from typing import Any


def calculate_lists_diff(
    local_lists: list[dict[str, Any]], remote_lists: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Calculate differences between local and remote Pi-hole lists."""
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

    # Find items that need changes
    to_change = [
        (local_by_address[addr], remote_by_address[addr])
        for addr in common_addresses
        if local_by_address[addr] != remote_by_address[addr]
    ]

    # Build result dictionary
    result = {}
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


def calculate_config_diff(
    local_config: Any, remote_config: Any, path: str = ""
) -> dict[str, dict[str, Any]]:
    """Recursively calculate differences between local and remote configurations.

    Only keys present in local configuration are considered for comparison.
    """
    differences: dict[str, dict[str, Any]] = {}

    if remote_config is None:
        remote_config = type(local_config)()

    if type(local_config) != type(remote_config):
        return {path: {"local": local_config, "remote": remote_config}}

    match local_config:
        case dict():
            for key, value in local_config.items():
                new_path = f"{path}.{key}" if path else key
                differences |= calculate_config_diff(
                    value, remote_config.get(key), new_path
                )

        case list():

            def make_hashable(item: Any) -> Any:
                """Convert nested structures to hashable types for comparison."""
                if isinstance(item, dict):
                    # Recursively make all values hashable before creating frozenset
                    return frozenset((k, make_hashable(v)) for k, v in item.items())
                if isinstance(item, list):
                    return tuple(make_hashable(x) for x in item)
                return item

            local_set = {make_hashable(x) for x in local_config}
            remote_set = {make_hashable(x) for x in remote_config or []}

            if local_set != remote_set:
                differences[path] = {"local": local_config, "remote": remote_config}

        case _:
            if local_config != remote_config:
                differences[path] = {"local": local_config, "remote": remote_config}

    return differences
