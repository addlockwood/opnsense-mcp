class OPNsenseMCPError(RuntimeError):
    """Base application error."""


class UnsupportedModuleError(OPNsenseMCPError):
    """Requested module or record type is not supported."""


class PlanApprovalError(OPNsenseMCPError):
    """A mutating action was attempted without explicit approval."""


class ValidationFailedError(OPNsenseMCPError):
    """Validation did not pass."""


class WorkspaceError(OPNsenseMCPError):
    """Workspace or git operations failed."""
