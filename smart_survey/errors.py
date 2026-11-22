"""Domain level exceptions mapped to HTTP status codes by the API layer."""


class SmartSurveyError(Exception):
    """Base class for all application errors."""

    status_code = 400

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(SmartSurveyError):
    status_code = 404


class ValidationError(SmartSurveyError):
    status_code = 422


class ConflictError(SmartSurveyError):
    status_code = 409


class AuthError(SmartSurveyError):
    status_code = 401
