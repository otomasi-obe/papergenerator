import sys


def pytest_configure(config):
    """Disable ROS plugins that cause conflicts."""
    try:
        if 'launch_testing_ros_pytest_entrypoint' in sys.modules:
            del sys.modules['launch_testing_ros_pytest_entrypoint']
    except Exception:
        pass
