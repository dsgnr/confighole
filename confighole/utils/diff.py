"""Configuration diffing utilities."""

from typing import Any

from confighole.utils.helpers import cnames_to_pihole_format, hosts_to_pihole_format


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
                    return frozenset(item.items())
                if isinstance(item, list):
                    return frozenset(make_hashable(x) for x in item)
                return item

            local_set = {make_hashable(x) for x in local_config}
            remote_set = {make_hashable(x) for x in remote_config or []}

            if local_set != remote_set:
                differences[path] = {"local": local_config, "remote": remote_config}

        case _:
            if local_config != remote_config:
                differences[path] = {"local": local_config, "remote": remote_config}

    return differences


def convert_diff_to_nested_dict(diff_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert flat diff dictionary to nested structure for Pi-hole updates.

    Converts hosts/cnameRecords back to string format expected by Pi-hole API.
    """
    result: dict[str, Any] = {}

    for path, change in diff_dict.items():
        local_value = change["local"]

        # Convert normalised data back to Pi-hole expected format
        if path.endswith("dns.hosts"):
            local_value = hosts_to_pihole_format(local_value)
        elif path.endswith("dns.cnameRecords"):
            local_value = cnames_to_pihole_format(local_value)

        # Build nested dictionary structure
        nested_dict = local_value
        for key in reversed(path.split(".")):
            nested_dict = {key: nested_dict}

        result = _merge_dictionaries(result, nested_dict)

    return result


def _merge_dictionaries(
    dict_a: dict[str, Any], dict_b: dict[str, Any]
) -> dict[str, Any]:
    """Recursively merge dictionary b into dictionary a."""
    for key, value in dict_b.items():
        if key in dict_a and isinstance(dict_a[key], dict) and isinstance(value, dict):
            dict_a[key] = _merge_dictionaries(dict_a[key], value)
        else:
            dict_a[key] = value

    return dict_a
