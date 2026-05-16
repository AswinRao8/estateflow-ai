class EstateFlowError(Exception):
    """Base for all domain exceptions."""


class InvalidStateTransitionError(EstateFlowError):
    def __init__(self, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Cannot transition lead from {from_state!r} to {to_state!r}")


class LeadNotFoundError(EstateFlowError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Lead not found: {identifier}")


class ListingNotFoundError(EstateFlowError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Listing not found: {identifier}")


class WhatsAppAPIError(EstateFlowError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"WhatsApp API error {status_code}: {detail}")
