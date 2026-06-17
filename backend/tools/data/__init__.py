# Import the submodule (NOT ``from .chart_api import chart_api``) so the
# ``tools.data.chart_api`` package attribute stays bound to the MODULE, not the
# Blueprint. Binding the Blueprint here would shadow the submodule and break
# attribute introspection / mock.patch("tools.data.chart_api.<x>").
# The Blueprint is imported via the submodule path: ``from tools.data.chart_api import chart_api``.
from . import chart_api  # noqa: F401
