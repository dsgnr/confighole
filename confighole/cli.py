"""Command-line interface for Pi-hole configuration manager."""

import argparse
import logging
import os
import sys
from typing import Any

import yaml

from confighole.core.daemon import ConfigHoleDaemon, run_daemon_from_env
from confighole.utils.config import (
    get_global_daemon_settings,
    load_yaml_config,
    merge_global_settings,
)
from confighole.utils.constants import DEFAULT_DAEMON_INTERVAL
from confighole.utils.tasks import process_instances


def setup_logging(verbosity: int) -> None:
    """Configure logging based on verbosity level."""
    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(verbosity, len(levels) - 1)]
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="ConfigHole - The Pi-hole configuration manager",
        epilog="Local config is always the source of truth.",
    )

    parser.add_argument(
        "-c", "--config", required=True, help="Path to the YAML configuration file"
    )
    parser.add_argument("-i", "--instance", help="Target a specific instance by name")

    # Operation modes (mutually exclusive)
    ops = parser.add_mutually_exclusive_group(required=True)
    ops.add_argument(
        "--dump", action="store_true", help="Fetch and display current configuration"
    )
    ops.add_argument(
        "--diff", action="store_true", help="Compare local vs remote configuration"
    )
    ops.add_argument(
        "--sync", action="store_true", help="Synchronise local configuration to Pi-hole"
    )
    ops.add_argument("--daemon", action="store_true", help="Run in daemon mode")

    # Options
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate changes without applying"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_DAEMON_INTERVAL,
        help="Daemon sync interval in seconds",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase verbosity"
    )

    return parser


def filter_instances(
    instances: list[dict[str, Any]], target: str | None = None
) -> list[dict[str, Any]]:
    """Filter instances by name."""
    if not target:
        return instances

    filtered = [inst for inst in instances if inst.get("name") == target]
    if not filtered:
        logging.error("No instance found with name %s", target)
        sys.exit(1)
    return filtered


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate command-line arguments."""
    if args.dry_run and not (args.sync or args.daemon):
        logging.error("--dry-run can only be used with --sync or --daemon")
        sys.exit(1)

    if args.interval != DEFAULT_DAEMON_INTERVAL and not args.daemon:
        logging.error("--interval can only be used with --daemon")
        sys.exit(1)


def get_operation_mode(args: argparse.Namespace) -> str:
    """Get operation mode from arguments."""
    for action in ("dump", "diff", "daemon"):
        if getattr(args, action):
            return action
    return "sync"


def resolve_settings(
    args: argparse.Namespace, global_settings: dict[str, Any]
) -> dict[str, Any]:
    """Resolve final settings from CLI args and global config."""
    return {
        "verbosity": args.verbose
        if args.verbose > 0
        else global_settings.get("verbosity", 1),
        "interval": (
            args.interval
            if args.interval != DEFAULT_DAEMON_INTERVAL
            else global_settings.get("daemon_interval", DEFAULT_DAEMON_INTERVAL)
        ),
        "dry_run": args.dry_run or global_settings.get("dry_run", False),
        "daemon_mode": args.daemon or global_settings.get("daemon_mode", False),
    }


def main() -> None:
    """Main entry point for the CLI application."""
    # Check for Docker daemon mode first, before parsing arguments
    if os.getenv("CONFIGHOLE_DAEMON_MODE", "").lower() == "true":
        setup_logging(int(os.getenv("CONFIGHOLE_VERBOSE", "1")))
        run_daemon_from_env()
        return

    parser = create_argument_parser()
    args = parser.parse_args()

    # Load config and resolve settings
    config = load_yaml_config(args.config)
    global_daemon_settings = get_global_daemon_settings(config)
    settings = resolve_settings(args, global_daemon_settings)

    # Apply daemon mode from config if not set via CLI
    if settings["daemon_mode"] and not args.daemon:
        args.daemon = True

    validate_arguments(args)
    setup_logging(settings["verbosity"])

    # Process instances
    all_instances = merge_global_settings(config)
    target_instances = filter_instances(all_instances, args.instance)

    if not target_instances:
        logging.error("No instances found in configuration")
        sys.exit(1)

    operation = get_operation_mode(args)

    if operation == "daemon":
        daemon = ConfigHoleDaemon(
            config_path=args.config,
            interval=settings["interval"],
            target_instance=args.instance,
            dry_run=settings["dry_run"],
        )
        daemon.run()
        return

    try:
        results = process_instances(
            target_instances, operation, dry_run=settings["dry_run"]
        )

        if results:
            print(
                yaml.dump(
                    results, sort_keys=False, allow_unicode=True, width=120, indent=2
                )
            )
        else:
            logging.info("No results to display")

    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as exc:
        logging.error("Unexpected error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
