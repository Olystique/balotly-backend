"""One shape for every error the API returns.

Every failure is ``{"detail": {"code": "...", "message": "..."}}``. The code
is a stable SNAKE_CASE string the frontend can branch on (VOTING_CLOSED and
CANDIDATE_NOT_FOUND need different screens); the message is plain language
for the person reading it. Never put a stack trace, a provider payload or a
bank detail in the message.
"""

from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    """Build (not raise) the HTTPException. Callers ``raise api_error(...)``."""
    detail: dict = {"code": code, "message": message}
    if extra:
        detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)
