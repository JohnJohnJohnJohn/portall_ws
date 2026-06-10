#!/usr/bin/env python3
"""Entry point for the frozen DeskPricer executable."""

import multiprocessing
import sys

from deskpricer.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main(sys.argv[1:])
