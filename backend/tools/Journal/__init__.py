"""Journal template generators package.

Some generators (ACM, APA, Elsevier, MDPI, Springer) use a bare
``from _docx_base import ...`` that only resolves when this directory is on
``sys.path`` (i.e. when run as a standalone script from inside the folder).
When imported as a package module (``tools.Journal.ACMgen``) that bare import
fails with ``ModuleNotFoundError: No module named '_docx_base'``.

Inject this package directory onto ``sys.path`` at import time so the shared
``_docx_base`` helper resolves regardless of how the generator is loaded.
"""
import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.append(_PKG_DIR)
