"""Data normalisation utilities for Pi-hole configurations."""

import logging
from typing import Any

from pihole_lib.models import PiHoleList

from confighole.utils.config import resolve_password
from confighole.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def validate_instance_config(instance_config: dict[str, Any]) -> None:
    """Validate instance configuration for required fields."""
    name = instance_config.get("name", "unknown")

    if not instance_config.get("base_url"):
        raise ConfigurationError(f"Instance '{name}' missing required 'base_url'")

    if not resolve_password(instance_config):
        raise ConfigurationError(
            f"Instance '{name}' has no password configured. "
            "Set 'password', 'password_env', or use ${ENV_VAR} syntax."
        )


def normalise_dns_hosts(hosts: list) -> list[dict[str, str]]:
    """Normalise DNS hosts to a consistent list format.

    Pi-hole accepts and returns the hosts as space separated values, ie: '192.168.1.1 rtr0'.
    But we use a list of dicts in our config to make it easier to maintain. Due to this, we must normalise them.
    """
    normalised = []
    required_keys = {"ip", "host"}
    for entry in hosts:
        # The local config is defined as a list of dicts
        if isinstance(entry, dict):
            # must have both ip and host keys
            if not required_keys.issubset(entry):
                raise ConfigurationError(
                    f"A host record must contain both {', and'.join(required_keys)} keys"
                )
            normalised.append(entry)
            continue

        # Pihole returns the records as space separated values
        if isinstance(entry, str) and " " in entry:
            ip, domain = entry.split(" ", 1)
            normalised.append({"ip": ip, "host": domain.strip()})
            continue

        # If we got this far, probably something went bad
        raise ConfigurationError("Failed to parse the hosts list")

    return normalised


def normalise_cname_records(cnames: list) -> list[dict[str, str]]:
    """Normalise CNAME records to a consistent list format.

    Pi-hole accepts and returns the hosts as comma separated values, ie: 'router,rtr0'.
    But we use a list of dicts in our config to make it easier to maintain. Due to this, we must normalise them.
    """
    normalised = []
    required_keys = {"name", "target"}
    for entry in cnames:
        # The local config is defined as a list of dicts
        if isinstance(entry, dict):
            if not required_keys.issubset(entry):
                raise ConfigurationError(
                    f"A cname record must contain both {', and'.join(required_keys)} keys"
                )
            normalised.append(entry)
            continue

        # Pihole returns the records as comma separated values
        if isinstance(entry, str) and "," in entry:
            name, target = map(str.strip, entry.split(",", 1))
            normalised.append({"name": name, "target": target})
            continue

        # If we got this far, probably something went bad
        raise ConfigurationError("Failed to parse the hosts list")

    return normalised


def normalise_remote_lists(lists: list[PiHoleList]) -> list[dict[str, str]]:
    """Normalise remote Pi-hole lists to consistent dictionary format."""
    return [
        {
            "address": list_item.address,
            "type": list_item.type.value,
            "comment": list_item.comment,
            "groups": list_item.groups,
            "enabled": list_item.enabled,
        }
        for list_item in lists
    ]


def normalise_configuration(config: dict[str, Any]) -> dict[str, Any]:
    """Normalise DNS-related configuration keys."""
    if not config:
        return {}

    dns_config = config.get("dns")
    if not isinstance(dns_config, dict):
        return config

    if "hosts" in dns_config:
        dns_config["hosts"] = normalise_dns_hosts(dns_config["hosts"])

    if "cnameRecords" in dns_config:
        dns_config["cnameRecords"] = normalise_cname_records(dns_config["cnameRecords"])

    return config


def hosts_to_pihole_format(hosts: list[dict[str, str]]) -> list[str]:
    """Convert normalised host dictionaries to Pi-hole string format."""
    return [f"{host['ip']} {host['host']}" for host in hosts]


def cnames_to_pihole_format(cnames: list[dict[str, str]]) -> list[str]:
    """Convert normalised CNAME dictionaries to Pi-hole string format."""
    return [f"{cname['name']},{cname['target']}" for cname in cnames]


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
