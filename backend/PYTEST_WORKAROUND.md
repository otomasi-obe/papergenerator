# Pytest Plugin Conflict - Known Issue

## Problem
Pytest fails to run due to plugin conflict with ROS (Robot Operating System) packages installed system-wide:

```
PluginValidationError: unknown hook 'pytest_launch_collect_makemodule' in plugin 
<module 'launch_testing_ros_pytest_entrypoint' from '/opt/ros/humble/lib/python3.10/site-packages/launch_testing_ros_pytest_entrypoint.py'>
```

## Root Cause
The `launch-testing-ros` plugin is auto-loaded by pytest because it's in the system PYTHONPATH. This plugin is incompatible with the current pytest version (9.0.3).

## Workarounds

### Option 1: Use Virtual Environment (Recommended)
Create an isolated virtual environment without system packages:

```bash
cd /home/sirobo/papergenerator/backend
python3 -m venv .venv --without-system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

### Option 2: Uninstall ROS Testing Plugin (if not needed)
If you don't need ROS testing functionality:

```bash
pip uninstall launch-testing-ros
```

### Option 3: Run Tests Individually
Run specific test files directly:

```bash
python3 -m pytest tests/unit/test_specific.py -p no:launch_testing_ros
```

## Status
- Issue documented: 2026-05-26
- Severity: P1 (High) - Blocks automated testing
- Impact: Cannot run full test suite, but individual tests can be run
- Recommended fix: Use virtual environment for development
