"""Live support chat (stub): a player WebSocket that answers with an automated acknowledgement.

There is no agent desk yet, so nothing is stored and no person reads the messages; the stub fixes
the wire protocol the apps speak. Suspended players may connect, because the suspension notice
tells them to contact support; revoked sessions may not.

Protocol (JSON text frames): the client sends `{"text": "..."}`; the server sends
`{"from": "support", "text": "...", "at": "<ISO-8601 UTC>"}`, starting with a greeting.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

import models
from core.security import get_current_user_token
from database import get_db

router = APIRouter()

MAX_TEXT = 1000
MAX_MESSAGES = 30
GREETING = "Hi, this is Osiris support. Tell us what happened and we'll get back to you."
RECEIVED = "Thanks. Live chat isn't staffed yet, so this message was not saved or read by a person."


def _player_id(websocket: WebSocket, db: Session) -> int | None:
    header = websocket.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        data = get_current_user_token(token)
    except HTTPException:
        return None
    if data["role"] != "player":
        return None
    user = db.query(models.User).filter(models.User.id == data["id"]).first()
    if user is None:
        return None
    if user.tokens_valid_after is not None:
        valid_after = int(user.tokens_valid_after.replace(tzinfo=timezone.utc).timestamp())
        if (data.get("iat") or 0) < valid_after:
            return None
    return user.id


def _say(text: str) -> dict:
    return {"from": "support", "text": text, "at": datetime.now(timezone.utc).isoformat()}


@router.websocket("/api/v2/support/ws")
async def support_chat(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    if _player_id(websocket, db) is None:
        # Before accept, so the handshake fails with 403 and the app treats it as signed out.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await websocket.send_json(_say(GREETING))
    try:
        for _ in range(MAX_MESSAGES):
            try:
                text = str(json.loads(await websocket.receive_text()).get("text", "")).strip()
            except (ValueError, AttributeError):
                await websocket.send_json(_say("That message could not be read. Send it as text."))
                continue
            if not text or len(text) > MAX_TEXT:
                await websocket.send_json(_say(f"Messages must be 1 to {MAX_TEXT} characters."))
                continue
            await websocket.send_json(_say(RECEIVED))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Message limit reached")
    except WebSocketDisconnect:
        return
