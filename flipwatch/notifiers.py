from __future__ import annotations

import logging
from typing import Protocol

import requests

from .config import NotifyConfig
from .evaluator import Verdict
from .models import Listing

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, title: str, body: str, listing: Listing | None = None) -> None: ...


def format_alert(listing: Listing, verdict: Verdict, watch_name: str, price_drop_from=None) -> tuple[str, str]:
    price = "no price" if listing.price is None else f"${listing.price:,.0f}"
    prefix = "PRICE DROP" if price_drop_from is not None else "FLIP"
    title = f"{prefix} [{listing.source}] {price} - {listing.title}"[:200]
    lines = [f"Watch: {watch_name}"]
    if price_drop_from is not None:
        lines.append(f"Was ${price_drop_from:,.0f}, now {price}")
    if verdict.est_profit is not None:
        lines.append(f"Est. profit ${verdict.est_profit:,.0f} ({verdict.roi:.0%} ROI)")
    if listing.location:
        lines.append(f"Location: {listing.location}")
    if verdict.signals:
        lines.append(f"Signals: {', '.join(verdict.signals)}")
    lines.append(listing.url)
    return title, "\n".join(lines)


class ConsoleNotifier:
    def send(self, title, body, listing=None):
        print(f"\n=== {title}\n{body}\n", flush=True)


class NtfyNotifier:
    """Push to your phone via the free ntfy app (https://ntfy.sh)."""

    def __init__(self, topic: str, server: str = "https://ntfy.sh"):
        self.topic = topic
        self.server = server.rstrip("/")

    def send(self, title, body, listing=None):
        payload = {"topic": self.topic, "title": title, "message": body, "priority": 4, "tags": ["moneybag"]}
        if listing is not None:
            payload["click"] = listing.url
            if listing.image_url:
                payload["attach"] = listing.image_url
        requests.post(self.server, json=payload, timeout=15).raise_for_status()


class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, title, body, listing=None):
        embed = {"title": title[:256], "description": body[:4000]}
        if listing is not None:
            embed["url"] = listing.url
            if listing.image_url:
                embed["thumbnail"] = {"url": listing.image_url}
        requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=15).raise_for_status()


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id

    def send(self, title, body, listing=None):
        requests.post(self.url, json={"chat_id": self.chat_id, "text": f"{title}\n\n{body}"}, timeout=15).raise_for_status()


def build_notifiers(cfg: NotifyConfig) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if cfg.console:
        notifiers.append(ConsoleNotifier())
    if cfg.ntfy_topic:
        notifiers.append(NtfyNotifier(cfg.ntfy_topic, cfg.ntfy_server))
    if cfg.discord_webhook:
        notifiers.append(DiscordNotifier(cfg.discord_webhook))
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        notifiers.append(TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id))
    return notifiers


def broadcast(notifiers: list[Notifier], title: str, body: str, listing: Listing | None = None) -> None:
    for n in notifiers:
        try:
            n.send(title, body, listing)
        except Exception as e:  # one broken channel shouldn't silence the others
            log.warning("%s failed: %s", type(n).__name__, e)
