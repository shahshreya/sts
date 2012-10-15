#!/bin/bash -

# If you have PyPy 1.6+ in a directory called pypy alongside pox.py, we
# use it.
# Otherwise, we try to use a Python interpreter called python2.7, which
# is a good idea if you're using Python from MacPorts, for example.
# We fall back to just "python" and hope that works.

''''echo -n
export OPT="-O"

if [ -x pypy/bin/pypy ]; then
  exec pypy/bin/pypy $OPT "$0" $FLG "$@"
fi

if [ "$(type -P python2.7)" != "" ]; then
  exec python2.7 $OPT "$0" "$@"
fi
exec python $OPT "$0" "$@"
'''

from sts.util.procutils import kill_procs

from sts.topology import FatTree, BufferedPatchPanel
from sts.control_flow import Fuzzer
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import Simulation
from pox.lib.recoco.recoco import Scheduler
import sts.snapshot as snapshot

import signal
import sys
import string
import subprocess
import time
import argparse
import logging
logging.basicConfig(level=logging.DEBUG)

log = logging.getLogger("sts")

description = """
Run a simulation.
Example usage:

$ %s -c config.fat_tree
""" % (sys.argv[0])

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=description)

parser.add_argument('-c', '--config',
                    default='config.fat_tree',
                    help='''experiment config module in the config/ '''
                         '''subdirectory, e.g. config.fat_tree''')

args = parser.parse_args()
# Allow configs to be specified as paths as well as module names
if args.config.endswith('.py'):
  args.config = args.config[:-3].replace("/", ".")

try:
  config = __import__(args.config, globals(), locals(), ["*"])
except ImportError:
  # try again, but look in the config director/module
  config = __import__("config.%s" % args.config, globals(), locals(), ["*"])

# If we get here, either *both* of the imports failed. config is defined if execution reaches here.

# For booting controllers
if hasattr(config, 'controllers'):
  controller_configs = config.controllers
else:
  raise RuntimeError("Must specify controllers in config file")

# For forwarding packets
if hasattr(config, 'patch_panel_class'):
  patch_panel_class = config.patch_panel_class
else:
  # We default to a BufferedPatchPanel
  patch_panel_class = BufferedPatchPanel

# For tracking the edges and vertices in our network
if hasattr(config, 'topology_class'):
  topology_class = config.topology_class
else:
  # We default to a FatTree
  topology_class = FatTree

# For constructing the topology object
if hasattr(config, 'topology_params'):
  topology_params = config.topology_params
else:
  # We default to no parameters
  topology_params = ""

# For controlling the simulation
if hasattr(config, 'control_flow'):
  simulator = config.control_flow
else:
  # We default to a Fuzzer
  simulator = Fuzzer()

# For snapshotting the controller's view of the network configuration
snapshot_service = snapshot.get_snapshotservice(controller_configs)

# For injecting dataplane packets into the simulated network
if hasattr(config, 'dataplane_trace') and config.dataplane_trace:
  dataplane_trace_path = config.dataplane_trace
else:
  # We default to no dataplane trace
  dataplane_trace_path = None

def handle_int(signal, frame):
  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % signal
  if simulation is not None:
    simulation.clean_up()
  sys.exit(0)

signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)

simulation = None

try:
  simulation = Simulation(controller_configs, topology_class,
                          topology_params, patch_panel_class,
                          dataplane_trace_path=dataplane_trace_path,
                          controller_sync_callback=simulator.get_sync_callback(),
                          snapshot_service=snapshot_service)
  simulator.simulate(simulation)
finally:
  if simulation is not None:
    simulation.clean_up()