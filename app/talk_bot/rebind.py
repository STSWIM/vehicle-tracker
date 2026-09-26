"""
Talk-Bot nach einer Neu-Registrierung der App automatisch wieder aktivieren.

Beim Abmelden einer ExApp loescht AppAPI deren Talk-Bots, beim Registrieren
entsteht ein neuer Bot, der in keiner Unterhaltung aktiv ist. Damit das
niemand nach jedem Deploy von Hand in den Unterhaltungseinstellungen
nachholen muss, merkt sich die App jede Unterhaltung, aus der Nachrichten
kommen (remember_conversation), und schaltet den Bot dort nach dem
Aktivieren wieder ein (rebind_bot). Das geht ueber die Talk-Bot-API als einer
der bekannten Nutzer der Unterhaltung - klappt nur, wenn er dort Moderator ist.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

from nc_py_api import AsyncNextcloudApp
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import TalkConversation

log = logging.getLogger(__name__)

BOT_API = "/ocs/v2.php/apps/spreed/api/v1/bot"
BOT_ENABLED = 1


def remember_conversation(db: Session, token: str, uid: str) -> None:
    entry = db.get(TalkConversation, (token, uid))
    if entry is None:
        db.add(TalkConversation(token=token, uid=uid))
    else:
        entry.zuletzt_gesehen = datetime.datetime.utcnow()
    db.commit()


def known_conversations(db: Session) -> dict[str, list[str]]:
    """token -> Nutzer, zuletzt aktive zuerst."""
    rows = db.execute(
        select(TalkConversation).order_by(TalkConversation.zuletzt_gesehen.desc())
    ).scalars()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row.token, []).append(row.uid)
    return result


async def _enable_in_conversation(nc: AsyncNextcloudApp, token: str, bot_name: str) -> bool:
    bots = await nc.ocs("GET", f"{BOT_API}/{token}")
    ours = next((b for b in bots if b.get("name") == bot_name), None)
    if ours is None:
        return False
    if ours.get("state") != BOT_ENABLED:
        await nc.ocs("POST", f"{BOT_API}/{token}/{ours['id']}")
    return True


async def rebind_bot(bot_name: str, client_for=lambda uid: AsyncNextcloudApp(user=uid)) -> int:
    """Aktiviert den Bot in allen bekannten Unterhaltungen; liefert die Anzahl
    der Unterhaltungen, in denen er danach aktiv ist."""
    db = SessionLocal()
    try:
        conversations = known_conversations(db)
        aktiv = 0
        for token, uids in conversations.items():
            for uid in uids:
                try:
                    if await _enable_in_conversation(client_for(uid), token, bot_name):
                        aktiv += 1
                        break
                except Exception as exc:  # kein Moderator, Unterhaltung geloescht, ...
                    log.info("Talk-Bot in %s als %s nicht aktivierbar: %s", token, uid, exc)
            else:
                # Unterhaltung geloescht? Dann beim naechsten Mal nicht mehr versuchen.
                if await _conversation_gone(client_for(uids[0]), token):
                    db.execute(delete(TalkConversation).where(TalkConversation.token == token))
                    db.commit()
        return aktiv
    finally:
        db.close()


async def _conversation_gone(nc: AsyncNextcloudApp, token: str) -> bool:
    try:
        await nc.ocs("GET", f"/ocs/v2.php/apps/spreed/api/v4/room/{token}")
        return False
    except Exception as exc:
        return getattr(exc, "status_code", None) == 404


def schedule_rebind(bot_name: str, delay: float = 5.0) -> None:
    """Im Hintergrund starten, damit der /enabled-Aufruf von AppAPI nicht auf
    die Talk-Anfragen warten muss."""

    async def run() -> None:
        await asyncio.sleep(delay)
        try:
            aktiv = await rebind_bot(bot_name)
            log.info("Talk-Bot in %d bekannten Unterhaltung(en) aktiv.", aktiv)
        except Exception:
            log.exception("Talk-Bot konnte nicht wieder aktiviert werden")

    asyncio.get_running_loop().create_task(run())
