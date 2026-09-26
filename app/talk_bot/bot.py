"""
Zentrale Talk-Bot-Instanz auf Basis von nc_py_api.talk_bot.AsyncTalkBot.

Ersetzt die fruehere handgestrickte HMAC-Signaturpruefung/-erzeugung
(vormals app/talk_bot/talk_api.py): AppAPI registriert den Bot beim
Aktivieren der ExApp automatisch und generiert selbst ein Secret - wir
muessen weder TALK_BOT_SECRET noch NEXTCLOUD_URL selbst verwalten.
"""
from __future__ import annotations

from nc_py_api import AsyncNextcloudApp
from nc_py_api.talk_bot import AsyncTalkBot

TALK_BOT_CALLBACK_URL = "/talk-bot/webhook"

bot = AsyncTalkBot(
    TALK_BOT_CALLBACK_URL,
    "Fahrzeug Buchführung",
    "Belegerfassung per Foto: Fahrzeug-Codewort, dann Tacho- und Belegfoto schicken.",
)


async def handle_enabled(enabled: bool, nc: AsyncNextcloudApp) -> None:
    """Registriert bzw. deregistriert den Talk-Bot passend zum App-Status und
    aktiviert ihn nach dem Registrieren in den bekannten Unterhaltungen."""
    await bot.enabled_handler(enabled, nc)
    if enabled:
        from app.talk_bot.rebind import schedule_rebind

        schedule_rebind(bot.display_name)
