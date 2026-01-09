"""Daemon mode for continuous Pi-hole configuration synchronisation."""

import logging
import os
import signal
import sys
import time
from typing import Any

from confighole.utils.config import load_yaml_config, merge_global_settings
from confighole.utils.constants import DEFAULT_DAEMON_INTERVAL
from confighole.utils.tasks import process_instances

logger = logging.getLogger(__name__)


class ConfigHoleDaemon:
    """Daemon for continuous Pi-hole configuration synchronisation."""

    def __init__(
        self,
        config_path: str,
        interval: int = DEFAULT_DAEMON_INTERVAL,
        target_instance: str | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialise the daemon."""
        self.config_path = config_path
        self.interval = interval
        self.target_instance = target_instance
        self.dry_run = dry_run
        self.running = False

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def _load_instances(self) -> list[dict[str, Any]]:
        """Load and filter instances from configuration."""
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
                        f"No instance found with name '{self.target_instance}'"
                    )
                    sys.exit(1)
                return filtered

            return all_instances

        except Exception as exc:
            logger.error(f"Failed to load configuration: {exc}")
            sys.exit(1)

    def _sync_instances(self) -> None:
        """Perform synchronisation of all target instances."""
        try:
            instances = self._load_instances()

            if not instances:
                logger.warning("No instances found in configuration")
                return

            logger.info(f"Starting sync for {len(instances)} instance(s)")
            results = process_instances(instances, "sync", dry_run=self.dry_run)

            if results:
                logger.info(f"Sync completed for {len(results)} instance(s)")
                for result in results:
                    name = result.get("name", "unknown")
                    changes_count = len(result.get("changes", {}))
                    action = "would be applied" if self.dry_run else "applied"
                    logger.info(f"  {name}: {changes_count} changes {action}")
            else:
                logger.info("No changes required for any instance")

        except Exception as exc:
            logger.error(f"Sync failed: {exc}")

    def run(self) -> None:
        """Run the daemon main loop."""
        logger.info("ConfigHole daemon starting...")
        logger.info(
            f"Config: {self.config_path}, Interval: {self.interval}s, Target: {self.target_instance or 'all'}, Dry run: {self.dry_run}"
        )

        self.running = True

        # Perform initial sync
        logger.info("Performing initial sync...")
        self._sync_instances()

        # Main daemon loop
        while self.running:
            try:
                logger.debug(f"Sleeping for {self.interval} seconds...")
                time.sleep(self.interval)

                if self.running:
                    self._sync_instances()

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                break
            except Exception as exc:
                logger.error(f"Unexpected error in daemon loop: {exc}")
                continue

        logger.info("ConfigHole daemon stopped")


def get_daemon_config_from_env() -> dict[str, Any]:
    """Get daemon configuration from environment variables."""
    return {
        "enabled": os.getenv("CONFIGHOLE_DAEMON_MODE", "false").lower() == "true",
        "interval": int(os.getenv("CONFIGHOLE_DAEMON_INTERVAL", "300")),
        "config_path": os.getenv("CONFIGHOLE_CONFIG_PATH"),
        "instance": os.getenv("CONFIGHOLE_INSTANCE"),
        "dry_run": os.getenv("CONFIGHOLE_DRY_RUN", "false").lower() == "true",
    }


def run_daemon_from_env() -> None:
    """Run daemon using environment variable configuration."""
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
