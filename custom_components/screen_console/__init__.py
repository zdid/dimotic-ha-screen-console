"""Console `screen` dans Home Assistant (panneau latéral + SSH local restreint)."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import websocket_api as console_ws
from .const import (
    CONF_ICON,
    CONF_KEY_PATH,
    CONF_TITLE,
    DEFAULT_ICON,
    DEFAULT_TITLE,
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_URL_PATH,
    STATIC_URL,
)
from .ssh_session import ensure_key

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = hass.data.setdefault(DOMAIN, {})
    await hass.async_add_executor_job(ensure_key, entry.data[CONF_KEY_PATH])
    title = entry.options.get(CONF_TITLE, DEFAULT_TITLE)
    icon = entry.options.get(CONF_ICON, DEFAULT_ICON)

    if not store.get("static_registered"):
        frontend_dir = str(Path(__file__).parent / "frontend")
        await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, frontend_dir, False)])
        console_ws.async_register(hass)
        store["static_registered"] = True

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{STATIC_URL}/panel.js?v=0.1.3",
        sidebar_title=title,
        sidebar_icon=icon,
        require_admin=True,
        config={"title": title},
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Titre ou icône modifiés : on recharge pour que le menu soit mis à jour."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    await console_ws.async_close_all(hass)
    return True
