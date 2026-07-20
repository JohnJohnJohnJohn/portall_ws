#!/usr/bin/env python3
"""Entry point for the frozen DeskPricer executable."""

import sys

from deskpricer.main import main

if __name__ == "__main__":
    # freeze_support() is called inside main() unconditionally so the same
    # code path is used by the console-script entry point and this frozen
    # entrypoint.
    main(sys.argv[1:])
