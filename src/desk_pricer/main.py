"""Uvicorn entrypoint."""

import argparse
import os
import sys

import uvicorn

from desk_pricer.app import create_app
from desk_pricer.logging_config import get_log_file

app = create_app()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeskPricer HTTP pricing service")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port to listen on (default: DESK_PRICER_PORT env var or 8765)",
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

    if args.port is not None:
        port = args.port
    else:
        raw_port = os.environ.get("DESK_PRICER_PORT", "8765")
        try:
            port = int(raw_port)
        except ValueError:
            print(f"ERROR: DESK_PRICER_PORT must be an integer, got: {raw_port}", file=sys.stderr)
            sys.exit(1)

    import logging

    log_file = get_log_file()
    print(f"DeskPricer starting on http://{args.host}:{port}", file=sys.stderr)
    logger = logging.getLogger("desk_pricer")
    has_file_handler = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    if has_file_handler:
        print(f"Logs written to: {log_file}", file=sys.stderr)
    else:
        print("Logs written to stderr (file logging unavailable)", file=sys.stderr)
    print("Change log path with: DESK_PRICER_LOG_DIR=<path>", file=sys.stderr)

    uvicorn.run(
        "desk_pricer.main:app",
        host=args.host,
        port=port,
        access_log=not args.quiet,
        log_level="info",
    )


if __name__ == "__main__":
    main(sys.argv[1:])
