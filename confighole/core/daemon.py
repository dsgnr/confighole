"""Daemon mode for continuous Pi-hole configuration synchronisation."""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from types import FrameType
from typing import Any

from confighole.utils.config import load_yaml_config, merge_global_settings
from confighole.utils.constants import DEFAULT_DAEMON_INTERVAL
from confighole.utils.tasks import process_instances

logger = logging.getLogger(__name__)


class ConfigHoleDaemon:
    """Daemon for continuous Pi-hole configuration synchronisation.

    Runs in a loop, periodically synchronising local configuration
    to one or more Pi-hole instances.
    """

    def __init__(
        self,
        config_path: str,
        interval: int = DEFAULT_DAEMON_INTERVAL,
        target_instance: str | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialise the daemon.

        Args:
            config_path: Path to the YAML configuration file.
            interval: Seconds between sync operations.
            target_instance: Optional instance name to target (None for all).
            dry_run: If True, only report what would change without applying.
        """
        self.config_path = config_path
        self.interval = interval
        self.target_instance = target_instance
        self.dry_run = dry_run
        self.running = False

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Received signal %d, shutting down gracefully...", signum)
        self.running = False

    def _load_instances(self) -> list[dict[str, Any]]:
        """Load and filter instances from configuration.

        Returns:
            List of instance configurations.

        Note:
            Exits the programme if configuration loading fails or
            target instance is not found.
        """
        try:
            config = load_yaml_config(self.config_path)
            all_instances = merge_global_settings(config)

            if self.target_instance:
                filtered = [
                    inst
                    for inst in all_instances
                    if inst.get("name") == self.target_instance
                ]
                if not filtered:
                    logger.error(
                        "No instance found with name '%s'", self.target_instance
                    )
                    sys.exit(1)
                return filtered

            return all_instances

        except Exception as exc:
            logger.error("Failed to load configuration: %s", exc)
            sys.exit(1)

    def _sync_instances(self) -> None:
        """Perform synchronisation of all target instances."""
        try:
            instances = self._load_instances()

            if not instances:
                logger.warning("No instances found in configuration")
                return

            logger.info("Starting sync for %d instance(s)", len(instances))
            results = process_instances(instances, "sync", dry_run=self.dry_run)

            if results:
                logger.info("Sync completed for %d instance(s)", len(results))
                action = "would be applied" if self.dry_run else "applied"
                for result in results:
                    name = result.get("name", "unknown")
                    changes_count = len(result.get("changes", {}))
                    logger.info("  %s: %d changes %s", name, changes_count, action)
            else:
                logger.info("No changes required for any instance")

        except Exception as exc:
            logger.error("Sync failed: %s", exc)

    def run(self) -> None:
        """Run the daemon main loop."""
        logger.info("ConfigHole daemon starting...")
        logger.info(
            "Config: %s, Interval: %ds, Target: %s, Dry run: %s",
            self.config_path,
            self.interval,
            self.target_instance or "all",
            self.dry_run,
        )

        self.running = True

        logger.info("Performing initial sync...")
        self._sync_instances()

        while self.running:
            try:
                logger.debug("Sleeping for %d seconds...", self.interval)
                time.sleep(self.interval)

                if self.running:
                    self._sync_instances()

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                break

            except Exception as exc:
                logger.error("Unexpected error in daemon loop: %s", exc)

        logger.info("ConfigHole daemon stopped")


def get_daemon_config_from_env() -> dict[str, Any]:
    """Get daemon configuration from environment variables.

    Returns:
        Dictionary containing daemon configuration.
    """
    return {
        "enabled": os.getenv("CONFIGHOLE_DAEMON_MODE", "false").lower() == "true",
        "interval": int(os.getenv("CONFIGHOLE_DAEMON_INTERVAL", "300")),
        "config_path": os.getenv("CONFIGHOLE_CONFIG_PATH"),
        "instance": os.getenv("CONFIGHOLE_INSTANCE"),
        "dry_run": os.getenv("CONFIGHOLE_DRY_RUN", "false").lower() == "true",
    }


def run_daemon_from_env() -> None:
    """Run daemon using environment variable configuration.

    Note:
        Exits the programme if daemon mode is not enabled or
        config path is not set.
    """
    config = get_daemon_config_from_env()

    if not config["enabled"]:
        logger.error("Daemon mode not enabled. Set CONFIGHOLE_DAEMON_MODE=true")
        sys.exit(1)

    if not config["config_path"]:
        logger.error("Config path required. Set CONFIGHOLE_CONFIG_PATH")
        sys.exit(1)

    daemon = ConfigHoleDaemon(
        config_path=config["config_path"],
        interval=config["interval"],
        target_instance=config["instance"],
        dry_run=config["dry_run"],
    )

    daemon.run()
