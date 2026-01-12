"""Data normalisation utilities for Pi-hole configurations."""

from __future__ import annotations

import logging
from typing import Any

from pihole_lib.models import Domain, PiHoleList

from confighole.utils.config import resolve_password
from confighole.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def validate_instance_config(instance_config: dict[str, Any]) -> None:
    """Validate instance configuration for required fields.

    Args:
        instance_config: Instance configuration dictionary.

    Raises:
        ConfigurationError: If required fields are missing or invalid.
    """
    name = instance_config.get("name", "unknown")

    if not instance_config.get("base_url"):
        raise ConfigurationError(f"Instance '{name}' missing required 'base_url'")

    if not resolve_password(instance_config):
        raise ConfigurationError(
            f"Instance '{name}' has no password configured. "
            "Set 'password', 'password_env', or use ${ENV_VAR} syntax."
        )


def normalise_dns_hosts(hosts: list[Any]) -> list[dict[str, str]]:
    """Normalise DNS hosts to a consistent list format.

    Pi-hole accepts and returns hosts as space-separated values (e.g. '192.168.1.1 rtr0').
    Local config uses a list of dicts for easier maintenance.

    Args:
        hosts: List of host entries (dicts or space-separated strings).

    Returns:
        List of normalised host dictionaries with 'ip' and 'host' keys.

    Raises:
        ConfigurationError: If host format is invalid.
    """
    normalised: list[dict[str, str]] = []
    required_keys = {"ip", "host"}

    for entry in hosts:
        if isinstance(entry, dict):
            if not required_keys.issubset(entry):
                raise ConfigurationError(
                    f"A host record must contain both {', and '.join(required_keys)} keys"
                )
            normalised.append(entry)

        elif isinstance(entry, str) and " " in entry:
            ip, domain = entry.split(" ", 1)
            normalised.append({"ip": ip, "host": domain.strip()})

        else:
            raise ConfigurationError("Failed to parse the hosts list")

    return normalised


def normalise_cname_records(cnames: list[Any]) -> list[dict[str, str]]:
    """Normalise CNAME records to a consistent list format.

    Pi-hole accepts and returns CNAMEs as comma-separated values (e.g. 'router,rtr0').
    Local config uses a list of dicts for easier maintenance.

    Args:
        cnames: List of CNAME entries (dicts or comma-separated strings).

    Returns:
        List of normalised CNAME dictionaries with 'name' and 'target' keys.

    Raises:
        ConfigurationError: If CNAME format is invalid.
    """
    normalised: list[dict[str, str]] = []
    required_keys = {"name", "target"}

    for entry in cnames:
        if isinstance(entry, dict):
            if not required_keys.issubset(entry):
                raise ConfigurationError(
                    f"A cname record must contain both {', and '.join(required_keys)} keys"
                )
            normalised.append(entry)

        elif isinstance(entry, str) and "," in entry:
            name, target = map(str.strip, entry.split(",", 1))
            normalised.append({"name": name, "target": target})

        else:
            raise ConfigurationError("Failed to parse the hosts list")

    return normalised


def normalise_remote_lists(lists: list[PiHoleList]) -> list[dict[str, Any]]:
    """Normalise remote Pi-hole lists to consistent dictionary format.

    Args:
        lists: List of PiHoleList objects from the Pi-hole API.

    Returns:
        List of normalised list dictionaries.
    """
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


def normalise_remote_domains(domains: list[Domain]) -> list[dict[str, Any]]:
    """Normalise remote Pi-hole domains to consistent dictionary format.

    Args:
        domains: List of Domain objects from the Pi-hole API.

    Returns:
        List of normalised domain dictionaries.
    """
    return [
        {
            "domain": domain_item.domain,
            "type": domain_item.type.value,
            "kind": domain_item.kind.value,
            "comment": domain_item.comment,
            "groups": domain_item.groups,
            "enabled": domain_item.enabled,
        }
        for domain_item in domains
    ]


def normalise_configuration(config: dict[str, Any]) -> dict[str, Any]:
    """Normalise DNS-related configuration keys.

    Converts hosts and CNAME records to their normalised dictionary format.

    Args:
        config: Configuration dictionary (may contain 'dns' section).

    Returns:
        Configuration with normalised DNS entries.
    """
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
    """Convert normalised host dictionaries to Pi-hole string format.

    Args:
        hosts: List of normalised host dictionaries.

    Returns:
        List of space-separated host strings for Pi-hole API.
    """
    return [f"{host['ip']} {host['host']}" for host in hosts]


def cnames_to_pihole_format(cnames: list[dict[str, str]]) -> list[str]:
    """Convert normalised CNAME dictionaries to Pi-hole string format.

    Args:
        cnames: List of normalised CNAME dictionaries.

    Returns:
        List of comma-separated CNAME strings for Pi-hole API.
    """
    return [f"{cname['name']},{cname['target']}" for cname in cnames]


def convert_diff_to_nested_dict(diff_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert flat diff dictionary to nested structure for Pi-hole updates.

    Converts hosts/cnameRecords back to string format expected by Pi-hole API.

    Args:
        diff_dict: Flat dictionary with dotted paths as keys.

    Returns:
        Nested dictionary structure suitable for Pi-hole API updates.
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

        result = _merge_dicts(result, nested_dict)

    return result


def _merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay dictionary into base dictionary.

    Args:
        base: Base dictionary to merge into.
        overlay: Dictionary to merge from.

    Returns:
        Merged dictionary.
    """
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _merge_dicts(base[key], value)
        else:
            base[key] = value

    return base
