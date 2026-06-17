from .jobs import publish_progress, progress_channel, cancel_key, _REDIS
from .paper_worker import run_generate_paper
from .generate_full import generate_paper, export_docx

# NOTE: do NOT re-export the ``jobs`` Blueprint here. Binding it as a package
# attribute would shadow the ``tools.paperfull.jobs`` submodule (which Python
# auto-binds when the submodule is imported above), breaking attribute-based
# introspection and mock.patch("tools.paperfull.jobs.<x>"). Import the Blueprint
# via the submodule path: ``from tools.paperfull.jobs import jobs``.
