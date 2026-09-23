"""
Duenner Client fuer die Nextcloud Talk Bot API: HMAC-Signatur fuer
ein- und ausgehende Nachrichten sowie das Versenden von Antworten.

Quelle/Referenz: https://nextcloud-talk.readthedocs.io/en/latest/bots/
Bitte vor dem produktiven Einsatz gegen die aktuelle Doku sowie die
tatsaechlich bei dir laufende Talk-Version pruefen – die genauen
Header-Namen ("...-Talk-Bot-..." vs. "...-Talk-...") haben sich in der
Vergangenheit zwischen Talk-Versionen leicht unterschieden.
"""
from __future__ import annotations

import hashlib
import hmac
import os

import httpx

TALK_BOT_SECRET = os.environ.get("TALK_BOT_SECRET", "")

# Alternative Header-Namen, je nach Talk-Version - beim Verifizieren werden
# beide Varianten akzeptiert (siehe webhook.py: get_header_any).
RANDOM_HEADER_CANDIDATES = ("X-Nextcloud-Talk-Bot-Random", "X-Nextcloud-Talk-Random")
SIGNATURE_HEADER_CANDIDATES = (
    "X-Nextcloud-Talk-Bot-Signature",
    "X-Nextcloud-Talk-Signature",
)
BACKEND_HEADER_CANDIDATES = ("X-Nextcloud-Talk-Backend",)


def compute_signature(random_value: str, body: bytes) -> str:
    digest = hmac.new(
        TALK_BOT_SECRET.encode("utf-8"),
        (random_value.encode("utf-8") + body),
        hashlib.sha256,
    )
    return digest.hexdigest()


def verify_signature(random_value: str, signature: str, body: bytes) -> bool:
    if not TALK_BOT_SECRET:
        # Ohne konfiguriertes Secret NICHT stillschweigend akzeptieren.
        return False
    expected = compute_signature(random_value, body)
    return hmac.compare_digest(expected, signature.lower())


def send_reply(
    nextcloud_url: str,
    conversation_token: str,
    message: str,
    *,
    reply_to: int | None = None,
) -> None:
    """Schickt eine Antwort in die Talk-Unterhaltung zurueck."""
    import secrets

    random_value = secrets.token_hex(32)
    body_params: dict = {"message": message}
    if reply_to is not None:
        body_params["replyTo"] = reply_to

    # Fuer die Signatur wird der ROHE Request-Body gebraucht; hier vereinfacht
    # ueber den urlencodierten Form-Body. Bei Problemen in der Praxis: den
    # tatsaechlich von httpx gesendeten Bytestring signieren, nicht das dict.
    body_bytes = httpx.QueryParams(body_params).__str__().encode("utf-8")
    signature = compute_signature(random_value, body_bytes)

    url = f"{nextcloud_url}/ocs/v2.php/apps/spreed/api/v1/bot/{conversation_token}/message"
    httpx.post(
        url,
        data=body_params,
        headers={
            "OCS-APIRequest": "true",
            "X-Nextcloud-Talk-Bot-Random": random_value,
            "X-Nextcloud-Talk-Bot-Signature": signature,
        },
        timeout=15.0,
    )
