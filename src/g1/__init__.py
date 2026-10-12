"""G1: a verification harness that runs beside a coding agent through the agent's hooks.

The core modules never name the host. Host knowledge lives in g1.adapter; install.py and __main__.py are the
composition layer that wires the adapter to the core; g1/host holds the files installed into the host.
"""

VERSION = "0.1.0"
RECORD_SCHEMA = 1
