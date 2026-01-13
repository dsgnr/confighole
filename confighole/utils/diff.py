"""Diffing logic for comparing local and remote Pi-hole configs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _calculate_items_diff(
    local_items: list[dict[str, Any]],
    remote_items: list[dict[str, Any]] | None,
    key_func: Callable[[dict[str, Any]], Any],
    compare_fields: list[str],
) -> dict[str, dict[str, Any]]:
    """Compare two lists of items and figure out what's different.

    Returns a dict with 'add', 'change', and 'remove' keys showing
    what needs to happen to make remote match local.
    """
    remote_items = remote_items or []

    local_by_key = {key_func(item): item for item in local_items}
    remote_by_key = {key_func(item): item for item in remote_items}

    local_keys = set(local_by_key)
    remote_keys = set(remote_by_key)

    to_add_keys = local_keys - remote_keys
    to_remove_keys = remote_keys - local_keys
    common_keys = local_keys & remote_keys

    to_change = [
        (local_by_key[key], remote_by_key[key])
        for key in common_keys
        if _items_differ(local_by_key[key], remote_by_key[key], compare_fields)
    ]

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
    """Check if two items differ on any of the specified fields."""
    for field in fields:
        local_value = local_item.get(field)
        remote_value = remote_item.get(field)

        if field == "groups":
            if _normalise_groups(local_value) != _normalise_groups(remote_value):
                return True
        elif field == "enabled":
            # Treat None as True (default enabled)
            if bool(local_value if local_value is not None else True) != bool(
                remote_value if remote_value is not None else True
            ):
                return True
        elif local_value != remote_value:
            return True

    return False


def _normalise_groups(value: Any) -> frozenset[int]:
    """Turn groups into a frozenset so we can compare regardless of order."""
    if isinstance(value, list):
        return frozenset(value)
    if value is not None:
        return frozenset([value])
    return frozenset([0])


def calculate_lists_diff(
    local_lists: list[dict[str, Any]],
    remote_lists: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Compare local and remote adlists, keyed by address."""
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
    """Compare local and remote domains, keyed by (domain, type, kind)."""
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
    """Compare local and remote groups, keyed by name."""
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
    """Compare local and remote clients, keyed by client identifier."""
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
    """Walk through configs recursively and find what's different.

    Only looks at keys that exist in local config (local is the source of truth).
    Returns a dict mapping dotted paths to {'local': ..., 'remote': ...}.
    """
    differences: dict[str, dict[str, Any]] = {}

    if remote_config is None:
        remote_config = (
            type(local_config)() if isinstance(local_config, dict | list) else None
        )

    if type(local_config) is not type(remote_config):
        return {path: {"local": local_config, "remote": remote_config}}

    if isinstance(local_config, dict):
        for key, value in local_config.items():
            new_path = f"{path}.{key}" if path else key
            differences |= calculate_config_diff(
                value, remote_config.get(key), new_path
            )

    elif isinstance(local_config, list):
        local_set = {_make_hashable(x) for x in local_config}
        remote_set = {_make_hashable(x) for x in remote_config or []}

        if local_set != remote_set:
            differences[path] = {"local": local_config, "remote": remote_config}

    elif local_config != remote_config:
        differences[path] = {"local": local_config, "remote": remote_config}

    return differences


def _make_hashable(item: Any) -> Any:
    """Make nested structures hashable so we can put them in sets."""
    if isinstance(item, dict):
        return frozenset((k, _make_hashable(v)) for k, v in item.items())
    if isinstance(item, list):
        return tuple(_make_hashable(x) for x in item)
    return item
