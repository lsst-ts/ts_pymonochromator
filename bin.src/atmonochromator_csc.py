#!/usr/bin/env python

import asyncio
import argparse

from lsst.ts.monochromator import monochromator_csc, version

parser = argparse.ArgumentParser(f"Start the ATMonochromator CSC")
parser.add_argument("--version", action="version", version=version.__version__)
parser.add_argument("-v", "--verbose", dest="verbose", action='count', default=0,
                    help="Set the verbosity for console logging.")

args = parser.parse_args()

csc = monochromator_csc.CSC()
asyncio.get_event_loop().run_until_complete(csc.done_task)
