"""Runs ConfigHole as a background service, syncing on a schedule."""

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
    """Keeps Pi-hole configs in sync by running periodic syncs in a loop."""

    def __init__(
        self,
        config_path: str,
        interval: int = DEFAULT_DAEMON_INTERVAL,
        target_instance: str | None = None,
        dry_run: bool = False,
    ) -> None:
        """Set up the daemon with config path and sync interval."""
        self.config_path = config_path
        self.interval = interval
        self.target_instance = target_instance
        self.dry_run = dry_run
        self.running = False

        # Register signal handlers for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._signal_handler)

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Catch SIGTERM/SIGINT and shut down cleanly."""
        logger.info("Received signal %d, shutting down gracefully...", signum)
        self.running = False

    def _load_instances(self) -> list[dict[str, Any]]:
        """Load instances from the config file, filtering if needed."""
        try:
            config = load_yaml_config(self.config_path)
            all_instances = merge_global_settings(config)

            if not self.target_instance:
                return all_instances

            filtered = [
                inst
                for inst in all_instances
                if inst.get("name") == self.target_instance
            ]
            if not filtered:
                logger.error("No instance found with name '%s'", self.target_instance)
                sys.exit(1)
            return filtered

        except Exception as exc:
            logger.error("Failed to load configuration: %s", exc)
            sys.exit(1)

    def _sync_instances(self) -> None:
        """Run a sync across all target instances."""
        try:
            instances = self._load_instances()

            if not instances:
                logger.warning("No instances found in configuration")
                return

            logger.info("Starting sync for %d instance(s)", len(instances))
            results = process_instances(instances, "sync", dry_run=self.dry_run)

            if results:
                action = "would be applied" if self.dry_run else "applied"
                logger.info("Sync completed for %d instance(s)", len(results))
                for result in results:
                    name = result.get("name", "unknown")
                    changes_count = len(result.get("changes", {}))
                    logger.info("  %s: %d changes %s", name, changes_count, action)
            else:
                logger.info("No changes required for any instance")

        except Exception as exc:
            logger.error("Sync failed: %s", exc)

    def run(self) -> None:
        """Start the daemon loop. Runs until interrupted."""
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
                logger.info("Sleeping for %d seconds...", self.interval)
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
    """Read daemon settings from environment variables."""

    def env_bool(key: str, default: str = "false") -> bool:
        return os.getenv(key, default).lower() == "true"

    return {
        "enabled": env_bool("CONFIGHOLE_DAEMON_MODE"),
        "interval": int(os.getenv("CONFIGHOLE_DAEMON_INTERVAL", "300")),
        "config_path": os.getenv("CONFIGHOLE_CONFIG_PATH"),
        "instance": os.getenv("CONFIGHOLE_INSTANCE"),
        "dry_run": env_bool("CONFIGHOLE_DRY_RUN"),
    }


def run_daemon_from_env() -> None:
    """Start the daemon using environment variables for config.

    Useful for running in Docker where you set env vars instead of CLI args.
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
