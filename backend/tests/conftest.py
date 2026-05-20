"""Pytest config — isolate from system pytest plugins (e.g. ROS launch_testing).

The host machine has /opt/ros/humble/lib/python3.10/site-packages on the
default sys.path which exposes a `launch_testing` pytest plugin entrypoint.
That plugin imports `yaml` which isn't installed in this venv. Disable
plugin autoload so the venv is fully self-contained.
"""
import os

os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
