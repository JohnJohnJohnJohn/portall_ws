"""Uvicorn entrypoint."""

import os

import uvicorn

from desk_pricer.app import create_app

app = create_app()


def main() -> None:
    port = int(os.environ.get("DESK_PRICER_PORT", "8765"))
    uvicorn.run(
        "desk_pricer.main:app",
        host="127.0.0.1",
        port=port,
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()
