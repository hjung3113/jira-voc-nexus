"""Local, dry-run Jira VOC triage proposal scaffold.

The package deliberately stops at a validated proposal.  Jira comment and
label publication is an integration boundary owned by a future adapter; this
scaffold never writes to Jira.
"""

from .service import NexusService

__all__ = ["NexusService"]
