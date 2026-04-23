"""Uvicorn entrypoint."""

import argparse
import logging
import os
import sys

import uvicorn

from deskpricer import __version__ as _APP_VERSION
from deskpricer.app import create_app
from deskpricer.logging_config import get_log_file

app = create_app()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeskPricer HTTP pricing service")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port to listen on (default: DESKPRICER_PORT env var or 8765)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host interface to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress request logs (useful when running as a background service)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    raw = args.port if args.port is not None else os.environ.get("DESKPRICER_PORT", "8765")
    try:
        port = int(raw)
    except ValueError:
        print(f"ERROR: DESKPRICER_PORT must be an integer, got: {raw}", file=sys.stderr)
        sys.exit(1)

    if not (1 <= port <= 65535):
        print(f"ERROR: port must be between 1 and 65535, got: {port}", file=sys.stderr)
        sys.exit(1)

    log_file = get_log_file()
    print(f"DeskPricer v{_APP_VERSION} starting on http://{args.host}:{port}", file=sys.stderr)
    logger = logging.getLogger("deskpricer")
    has_file_handler = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    if has_file_handler:
        print(f"Logs written to: {log_file}", file=sys.stderr)
    else:
        print("Logs written to stderr (file logging unavailable)", file=sys.stderr)
    print("Change log path with: DESKPRICER_LOG_DIR=<path>", file=sys.stderr)

    uvicorn.run(
        "deskpricer.main:app",
        host=args.host,
        port=port,
        access_log=not args.quiet,
        log_level="info",
    )


if __name__ == "__main__":
    main(sys.argv[1:])
