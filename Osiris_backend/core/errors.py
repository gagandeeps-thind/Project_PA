"""Error shapes shared by the v2 endpoints."""

from fastapi import HTTPException



def _api_error(status_code: int, code: str, message: str) -> HTTPException:
    """v2 structured error: `detail` is {code, message} so clients can branch on `code`."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
