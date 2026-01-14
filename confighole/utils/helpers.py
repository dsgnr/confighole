"""Helpers for normalising Pi-hole config data between local and remote formats."""

from __future__ import annotations

import logging
from typing import Any

from pihole_lib.models.client_mgmt import Client
from pihole_lib.models.domains import Domain
from pihole_lib.models.groups import Group
from pihole_lib.models.lists import PiHoleList

from confighole.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def normalise_dns_hosts(hosts: list[Any]) -> list[dict[str, str]]:
    """Convert DNS hosts to a consistent dict format.

    Pi-hole uses space-separated strings like '192.168.1.1 router.local',
    but we prefer dicts with 'ip' and 'host' keys for easier editing.
    Accepts either format and returns the dict version.
    """
    required_keys = frozenset({"ip", "host"})
    normalised: list[dict[str, str]] = []

    for entry in hosts:
        if isinstance(entry, dict):
            if not required_keys <= entry.keys():
                raise ConfigurationError(
                    f"A host record must contain both {' and '.join(required_keys)} keys"
                )
            normalised.append(entry)
        elif isinstance(entry, str) and " " in entry:
            ip, domain = entry.split(" ", 1)
            normalised.append({"ip": ip, "host": domain.strip()})
        else:
            raise ConfigurationError("Failed to parse the hosts list")

    return normalised


def normalise_cname_records(cnames: list[Any]) -> list[dict[str, str]]:
    """Convert CNAME records to a consistent dict format.

    Pi-hole uses comma-separated strings like 'alias.local,target.local',
    but we prefer dicts with 'name' and 'target' keys.
    Accepts either format and returns the dict version.
    """
    required_keys = frozenset({"name", "target"})
    normalised: list[dict[str, str]] = []

    for entry in cnames:
        if isinstance(entry, dict):
            if not required_keys <= entry.keys():
                raise ConfigurationError(
                    f"A cname record must contain both {' and '.join(required_keys)} keys"
                )
            normalised.append(entry)
        elif isinstance(entry, str) and "," in entry:
            name, target = entry.split(",", 1)
            normalised.append({"name": name.strip(), "target": target.strip()})
        else:
            raise ConfigurationError("Failed to parse the hosts list")

    return normalised


def normalise_remote_lists(lists: list[PiHoleList]) -> list[dict[str, Any]]:
    """Turn PiHoleList objects from the API into plain dicts."""
    return [
        {
            "address": item.address,
            "type": item.type.value,
            "comment": item.comment,
            "groups": item.groups,
            "enabled": item.enabled,
        }
        for item in lists
    ]


def normalise_remote_domains(domains: list[Domain]) -> list[dict[str, Any]]:
    """Turn Domain objects from the API into plain dicts."""
    return [
        {
            "domain": item.domain,
            "type": item.type.value,
            "kind": item.kind.value,
            "comment": item.comment,
            "groups": item.groups,
            "enabled": item.enabled,
        }
        for item in domains
    ]


def normalise_remote_groups(groups: list[Group]) -> list[dict[str, Any]]:
    """Turn Group objects from the API into plain dicts."""
    return [
        {
            "name": item.name,
            "comment": item.comment,
            "enabled": item.enabled,
        }
        for item in groups
    ]


def normalise_remote_clients(clients: list[Client]) -> list[dict[str, Any]]:
    """Turn Client objects from the API into plain dicts."""
    return [
        {
            "client": item.client,
            "comment": item.comment,
            "groups": item.groups,
        }
        for item in clients
    ]


def normalise_configuration(config: dict[str, Any]) -> dict[str, Any]:
    """Normalise the DNS section of a config (hosts and CNAMEs)."""
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
    """Convert host dicts back to Pi-hole's space-separated format."""
    return [f"{h['ip']} {h['host']}" for h in hosts]


def cnames_to_pihole_format(cnames: list[dict[str, str]]) -> list[str]:
    """Convert CNAME dicts back to Pi-hole's comma-separated format."""
    return [f"{c['name']},{c['target']}" for c in cnames]


def convert_diff_to_nested_dict(diff_dict: dict[str, Any]) -> dict[str, Any]:
    """Turn a flat diff (with dotted paths) into a nested dict for the API.

    Also converts hosts/CNAMEs back to the string format Pi-hole expects.
    """
    result: dict[str, Any] = {}

    for path, change in diff_dict.items():
        local_value = change["local"]

        # Convert normalised data back to Pi-hole expected format
        if path.endswith("dns.hosts"):
            local_value = hosts_to_pihole_format(local_value)
        elif path.endswith("dns.cnameRecords"):
            local_value = cnames_to_pihole_format(local_value)

        # Build nested dictionary structure from dotted path
        keys = path.split(".")
        nested = local_value
        for key in reversed(keys):
            nested = {key: nested}

        result = _merge_dicts(result, nested)

    return result


def _merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep merge overlay into base, modifying base in place."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _merge_dicts(base[key], value)
        else:
            base[key] = value

    return base
