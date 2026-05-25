from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote

import aiohttp

from app.config import Settings


DISCORD_API_BASE_URL = "https://discord.com/api/v10"


class DiscordInviteError(RuntimeError):
    """Raised when Discord cannot create a single-use invite."""


@dataclass(frozen=True)
class DiscordInvite:
    code: str
    url: str


async def create_discord_invite(
    settings: Settings,
    *,
    reason: Optional[str] = None,
) -> DiscordInvite:
    bot_token = getattr(settings, "discord_bot_token", None)
    channel_id = getattr(settings, "discord_invite_channel_id", None)
    if not bot_token or not channel_id:
        raise DiscordInviteError(
            "DISCORD_BOT_TOKEN and DISCORD_INVITE_CHANNEL_ID are required for unique invites."
        )

    max_age_seconds = int(getattr(settings, "discord_invite_max_age_seconds", 604800))
    payload = {
        "max_age": max_age_seconds,
        "max_uses": 1,
        "temporary": False,
        "unique": True,
    }
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    if reason:
        headers["X-Audit-Log-Reason"] = quote(reason[:512])

    url = f"{DISCORD_API_BASE_URL}/channels/{channel_id}/invites"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
        data = await _post_invite_with_retries(session, url, payload, headers)

    code = data.get("code")
    if not isinstance(code, str) or not code:
        raise DiscordInviteError("Discord response did not include an invite code.")

    invite_url = data.get("url")
    if not isinstance(invite_url, str) or not invite_url:
        invite_url = f"https://discord.gg/{code}"

    return DiscordInvite(code=code, url=invite_url)


async def _post_invite_with_retries(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    last_error: Optional[str] = None
    for attempt in range(3):
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                data = await _json_or_text(response)
                if 200 <= response.status < 300:
                    if not isinstance(data, dict):
                        raise DiscordInviteError("Discord returned a non-JSON invite response.")
                    return data

                last_error = _format_discord_error(response.status, data)
                if response.status == 429:
                    retry_after = _retry_after_seconds(data)
                    await asyncio.sleep(retry_after)
                    continue
                if response.status in {500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                break
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = str(exc) or exc.__class__.__name__
            if attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            break

    raise DiscordInviteError(last_error or "Discord invite request failed.")


async def _json_or_text(response: aiohttp.ClientResponse) -> Any:
    try:
        return await response.json()
    except (aiohttp.ContentTypeError, ValueError):
        return await response.text()


def _retry_after_seconds(data: Any) -> float:
    if isinstance(data, dict):
        retry_after = data.get("retry_after")
        if isinstance(retry_after, (int, float)):
            return min(max(float(retry_after), 0.5), 5.0)
    return 1.0


def _format_discord_error(status: int, data: Any) -> str:
    if isinstance(data, dict):
        message = data.get("message")
        code = data.get("code")
        if message:
            return f"Discord API error {status}: {message} ({code})"
    if isinstance(data, str) and data:
        return f"Discord API error {status}: {data[:300]}"
    return f"Discord API error {status}"
