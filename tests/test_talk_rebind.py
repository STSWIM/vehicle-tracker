"""Talk-Bot nach Neu-Registrierung automatisch wieder aktivieren."""
import asyncio

from app.models import TalkConversation
from app.talk_bot.rebind import BOT_API, known_conversations, rebind_bot, remember_conversation

BOT = "Fahrzeug Buchführung"


class FakeError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeTalk:
    """Nachgebildete Talk-Bot-API: je Unterhaltung Moderatoren und Bot-Status."""

    def __init__(self, rooms):
        self.rooms = rooms  # token -> {"moderators": {...}, "state": 0|1}
        self.calls = []

    def client(self, uid):
        talk = self

        class Client:
            async def ocs(self, method, path, **kwargs):
                talk.calls.append((uid, method, path))
                token = path.split("/")[-2 if method == "POST" else -1]
                room = talk.rooms.get(token)
                if room is None:
                    raise FakeError(404)
                if uid not in room["moderators"]:
                    raise FakeError(403)
                if path.startswith("/ocs/v2.php/apps/spreed/api/v4/room/"):
                    return {"token": token}
                if method == "GET":
                    return [{"id": 7, "name": "Anderer Bot", "state": 1},
                            {"id": 42, "name": BOT, "state": room["state"]}]
                room["state"] = 1
                return {}

        return Client()


def test_unterhaltung_merken(db_session):
    remember_conversation(db_session, "abc", "alice")
    remember_conversation(db_session, "abc", "bob")
    remember_conversation(db_session, "abc", "alice")
    assert db_session.query(TalkConversation).count() == 2
    assert known_conversations(db_session) == {"abc": ["alice", "bob"]}


def test_bot_wird_als_moderator_wieder_aktiviert(db_session):
    remember_conversation(db_session, "familie", "kind")      # kein Moderator
    remember_conversation(db_session, "familie", "michael")   # Moderator
    remember_conversation(db_session, "schon-aktiv", "michael")
    talk = FakeTalk({
        "familie": {"moderators": {"michael"}, "state": 0},
        "schon-aktiv": {"moderators": {"michael"}, "state": 1},
    })

    aktiv = asyncio.run(rebind_bot(BOT, client_for=talk.client))

    assert aktiv == 2
    assert talk.rooms["familie"]["state"] == 1
    assert ("michael", "POST", f"{BOT_API}/familie/42") in talk.calls
    # bereits aktiver Bot wird nicht erneut eingeschaltet
    assert ("michael", "POST", f"{BOT_API}/schon-aktiv/42") not in talk.calls


def test_geloeschte_unterhaltung_wird_vergessen(db_session):
    remember_conversation(db_session, "weg", "michael")
    remember_conversation(db_session, "kein-mod", "kind")
    talk = FakeTalk({"kein-mod": {"moderators": set(), "state": 0}})

    assert asyncio.run(rebind_bot(BOT, client_for=talk.client)) == 0

    # geloeschte Unterhaltung vergessen, nur fehlende Rechte merken wir uns weiter
    assert set(known_conversations(db_session)) == {"kein-mod"}
