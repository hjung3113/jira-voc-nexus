"""Small, safe exception hierarchy for the local scaffold."""


class NexusError(Exception):
    """Base class whose messages are safe to show at the CLI boundary."""


class InputError(NexusError):
    """The normalized event or corpus did not satisfy its input contract."""


class ProposalValidationError(NexusError):
    """An engine returned a proposal outside the grounded output contract."""


class EngineError(NexusError):
    """The selected proposal engine failed or returned unusable output."""


class StateConflictError(NexusError):
    """An event id was already processed with a different payload."""


class StateError(NexusError):
    """Durable local state could not be read or updated safely."""
