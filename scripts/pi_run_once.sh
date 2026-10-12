#!/bin/sh
set -eu
cd /home/pi/Desktop/PetMind_Test
exec .venv/bin/python device_agent.py --base http://127.0.0.1:18010 --cache commands.db --once "$@"
