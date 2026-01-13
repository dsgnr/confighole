"""Handles loading config files and resolving authentication."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import yaml

from confighole.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def resolve_password(instance_config: dict[str, Any]) -> str | None:
    """Figure out the password from config, supporting env vars or direct values.

    You can set passwords three ways:
    - Environment variable syntax: password: ${VAR_NAME}
    - Direct value: password: "my-secret"
    - Env var reference: password_env: "VAR_NAME"
    """
    password = instance_config.get("password")

    # Handle environment variable syntax: ${VAR_NAME}
    if (
        isinstance(password, str)
        and password.startswith("${")
        and password.endswith("}")
    ):
        return os.getenv(password[2:-1])

    # Direct password
    if password:
        return str(password)

    # Fallback to password_env
    if password_env := instance_config.get("password_env"):
        return os.getenv(password_env)

    return None


def validate_instance_config(instance_config: dict[str, Any]) -> None:
    """Check that an instance config has all the required fields.

    Raises ConfigurationError if base_url or password is missing.
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
    """Load a YAML config file. Exits with code 1 if it fails."""
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
    """Apply global settings to each instance, letting instance values win.

    Daemon-specific settings (daemon_mode, daemon_interval, etc.) are
    intentionally excluded since they don't belong on individual instances.
    """
    global_settings = config.get("global", {})
    instances = config.get("instances", [])

    # Settings that don't apply to individual instances
    daemon_only_settings = frozenset(
        {"daemon_mode", "daemon_interval", "verbosity", "dry_run"}
    )

    # Filter global settings once, excluding daemon-only keys
    applicable_globals = {
        k: v for k, v in global_settings.items() if k not in daemon_only_settings
    }

    return [{**applicable_globals, **instance} for instance in instances]


def get_global_daemon_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Pull out daemon-specific settings from the global config section."""
    global_settings = config.get("global", {})

    defaults = {
        "daemon_mode": False,
        "daemon_interval": 300,
        "verbosity": 1,
        "dry_run": False,
    }

    return {key: global_settings.get(key, default) for key, default in defaults.items()}
