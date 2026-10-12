"""Commandes WebSocket de la console (réservées aux administrateurs de HA)."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import CONF_HOST, CONF_KEY_PATH, CONF_PORT, CONF_USERNAME, DOMAIN, MAX_SESSIONS
from .ssh_session import ScreenSession, SshTarget, list_sessions, valid_session_name

_LOGGER = logging.getLogger(__name__)

MAX_INPUT_BYTES = 65536


def _target(hass: HomeAssistant) -> SshTarget | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    data = entries[0].data
    return SshTarget(data[CONF_HOST], data[CONF_PORT], data[CONF_USERNAME], data[CONF_KEY_PATH])


def _sessions(hass: HomeAssistant) -> dict[str, tuple[Any, ScreenSession]]:
    return hass.data.setdefault(DOMAIN, {}).setdefault("sessions", {})


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_connect)
    websocket_api.async_register_command(hass, ws_input)
    websocket_api.async_register_command(hass, ws_resize)


async def async_close_all(hass: HomeAssistant) -> None:
    for _, session in list(_sessions(hass).values()):
        await session.close()
    _sessions(hass).clear()


@websocket_api.websocket_command({vol.Required("type"): "screen_console/list"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    target = _target(hass)
    if target is None:
        connection.send_error(msg["id"], "not_configured", "Intégration Screen Console non configurée.")
        return
    try:
        sessions = await list_sessions(target)
    except Exception as err:  # noqa: BLE001 - message renvoyé tel quel à l'écran d'administration
        connection.send_error(msg["id"], "ssh_failed", f"Liste des sessions impossible : {err}")
        return
    connection.send_result(msg["id"], {"sessions": sessions})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "screen_console/connect",
        vol.Required("session_id"): str,
        vol.Required("name"): str,
        vol.Optional("cols", default=80): vol.All(int, vol.Range(min=10, max=500)),
        vol.Optional("rows", default=24): vol.All(int, vol.Range(min=3, max=200)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_connect(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    target = _target(hass)
    sessions = _sessions(hass)
    if target is None:
        connection.send_error(msg["id"], "not_configured", "Intégration Screen Console non configurée.")
        return
    if not valid_session_name(msg["name"]):
        connection.send_error(msg["id"], "invalid_name", "Nom de session invalide.")
        return
    if msg["session_id"] in sessions or len(sessions) >= MAX_SESSIONS:
        connection.send_error(msg["id"], "too_many", f"{MAX_SESSIONS} sessions ouvertes au maximum.")
        return

    msg_id = msg["id"]
    session_id = msg["session_id"]

    async def on_output(data: bytes) -> None:
        connection.send_message(
            websocket_api.event_message(msg_id, {"type": "output", "data": base64.b64encode(data).decode()})
        )

    async def on_close(reason: str) -> None:
        sessions.pop(session_id, None)
        connection.send_message(websocket_api.event_message(msg_id, {"type": "closed", "reason": reason}))

    session = ScreenSession(target, msg["name"])
    try:
        await session.start(msg["cols"], msg["rows"], on_output, on_close)
    except Exception as err:  # noqa: BLE001
        await session.close()
        connection.send_error(msg["id"], "ssh_failed", f"Connexion impossible : {err}")
        return

    sessions[session_id] = (connection, session)

    @callback
    def unsubscribe() -> None:
        entry = sessions.pop(session_id, None)
        if entry is not None:
            hass.async_create_task(entry[1].close())

    connection.subscriptions[msg_id] = unsubscribe
    connection.send_result(msg_id)


def _owned(hass: HomeAssistant, connection: websocket_api.ActiveConnection, session_id: str) -> ScreenSession | None:
    entry = _sessions(hass).get(session_id)
    if entry is None or entry[0] is not connection:
        return None
    return entry[1]


@websocket_api.websocket_command(
    {vol.Required("type"): "screen_console/input", vol.Required("session_id"): str, vol.Required("data"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_input(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    session = _owned(hass, connection, msg["session_id"])
    if session is None:
        connection.send_error(msg["id"], "no_session", "Session inconnue.")
        return
    try:
        data = base64.b64decode(msg["data"], validate=True)
    except ValueError:
        connection.send_error(msg["id"], "bad_data", "Données invalides.")
        return
    if len(data) > MAX_INPUT_BYTES:
        connection.send_error(msg["id"], "too_big", "Envoi trop volumineux.")
        return
    await session.write(data)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "screen_console/resize",
        vol.Required("session_id"): str,
        vol.Required("cols"): vol.All(int, vol.Range(min=10, max=500)),
        vol.Required("rows"): vol.All(int, vol.Range(min=3, max=200)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_resize(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    session = _owned(hass, connection, msg["session_id"])
    if session is None:
        connection.send_error(msg["id"], "no_session", "Session inconnue.")
        return
    await session.resize(msg["cols"], msg["rows"])
    connection.send_result(msg["id"])
