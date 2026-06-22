#!/bin/bash
# Wrapper script to run pytest without ROS plugin interference
# Created: Cycle 57 (2026-05-25)
# Purpose: Enable test execution by preventing plugin auto-discovery
#
# Usage:
#   ./run_tests.sh tests/test_slr_worker.py -v
#   ./run_tests.sh tests/ -v
#   ./run_tests.sh tests/ --cov=. --cov-report=html

cd "$(dirname "$0")"

# Disable plugin auto-discovery to prevent ROS plugin loading
# This prevents launch-testing-ros-0.19.13 from loading, which is
# incompatible with pytest 9.0.3 and causes INTERNALERROR
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

# Run pytest with all arguments passed through
python3 -m pytest "$@"
