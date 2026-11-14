"""Command-line entry point for processing and verifying runs."""

import argparse
import logging
from pathlib import Path

from . import __version__
from .config import Settings, ToolkitError
from .pipeline import run, verify


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate and reconcile retail order-line exports.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    process = commands.add_parser("run", help="Process CSV and JSON inputs in priority order.")
    process.add_argument("inputs", type=Path, nargs="+")
    check = commands.add_parser("verify", help="Check a run's artifact hashes.")
    check.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)

    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    logger = logging.getLogger("business_toolkit")
    try:
        if args.command == "verify":
            verify(args.run_dir)
            print("Artifact checksums verified.")
            return 0
        settings = Settings.from_env()
        logger.setLevel(settings.log_level)
        destination, report = run(args.inputs, settings)
    except ToolkitError as error:
        logger.error("%s", error)
        return 1
    except (OSError, ValueError) as error:
        logger.error("File operation failed (%s). Check paths and permissions.", type(error).__name__)
        return 1
    print(f"{report['decision']} ({report['reason']}) | accepted={report['accepted']} | "
          f"rejected={report['rejected']} | {destination}")
    return 0 if report["decision"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
