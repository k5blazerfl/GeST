"""Software-management module — the Portage front for GeST.

Queries use the in-process Portage Python API (fast, structured, no output
scraping). Mutations (building/merging, editing /etc/portage) are the job of
the privileged backend and are invoked through ``backend_client``.
"""

from gest.core.software import reader
from gest.core.software.model import Package, SearchResult, UseFlag

__all__ = ["reader", "Package", "SearchResult", "UseFlag"]
