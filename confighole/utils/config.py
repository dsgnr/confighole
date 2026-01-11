"""Configuration loading and authentication utilities."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import yaml

from confighole.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def resolve_password(instance_config: dict[str, Any]) -> str | None:
    """Resolve Pi-hole password from instance configuration or environment.

    Supports three methods of password configuration:
    1. Environment variable syntax: password: ${VAR_NAME}
    2. Direct password value: password: "my-secret"
    3. Environment variable reference: password_env: "VAR_NAME"

    Args:
        instance_config: Instance configuration dictionary.

    Returns:
        Resolved password string, or None if not found.
    """
    password = instance_config.get("password")

    # Handle environment variable syntax: ${VAR_NAME}
    if (
        isinstance(password, str)
        and password.startswith("${")
        and password.endswith("}")
    ):
        env_var = password[2:-1]
        return os.getenv(env_var)

    # Direct password
    if password:
        return str(password)

    # Fallback to password_env
    password_env = instance_config.get("password_env")
    if password_env:
        return os.getenv(password_env)

    return None


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


def load_yaml_config(file_path: str) -> dict[str, Any]:
    """Load and validate a YAML configuration file.

    Args:
        file_path: Path to the YAML configuration file.

    Returns:
        Parsed configuration dictionary.

    Note:
        Exits the programme with code 1 if loading fails.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict):
            raise ValueError("Top-level YAML must be a mapping")

        return config

    except Exception as exc:
        logger.error("Failed to load config %s: %s", file_path, exc)
        sys.exit(1)


def merge_global_settings(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge global settings into instance configurations.

    Global settings are applied to all instances unless overridden
    at the instance level. Daemon-specific settings are excluded
    from instance merging.

    Args:
        config: Full configuration dictionary with 'global' and 'instances' keys.

    Returns:
        List of instance configurations with global settings merged in.
    """
    global_settings = config.get("global", {})
    instances = config.get("instances", [])

    # Settings that don't apply to individual instances
    daemon_only_settings = {"daemon_mode", "daemon_interval", "verbosity", "dry_run"}

    merged_instances = []
    for instance in instances:
        merged = dict(instance)

        # Apply global settings, allowing instance overrides
        for key, value in global_settings.items():
            if key not in merged and key not in daemon_only_settings:
                merged[key] = value

        merged_instances.append(merged)

    return merged_instances


def get_global_daemon_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Extract daemon-specific settings from global configuration.

    Args:
        config: Full configuration dictionary.

    Returns:
        Dictionary containing daemon-specific settings with defaults applied.
    """
    global_settings = config.get("global", {})

    return {
        "daemon_mode": global_settings.get("daemon_mode", False),
        "daemon_interval": global_settings.get("daemon_interval", 300),
        "verbosity": global_settings.get("verbosity", 1),
        "dry_run": global_settings.get("dry_run", False),
    }
