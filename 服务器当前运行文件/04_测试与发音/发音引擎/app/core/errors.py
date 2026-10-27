class EngineError(Exception):
    """Base error that is safe to expose through the API."""

    def __init__(self, message: str, code: str = "ENGINE_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class AudioValidationError(EngineError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "INVALID_AUDIO")


class ModelNotReadyError(EngineError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "MODEL_NOT_READY")


class UnknownWordError(EngineError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "UNKNOWN_WORD")
