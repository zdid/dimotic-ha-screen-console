"""Console `screen` dans Home Assistant (panneau latéral + SSH local restreint)."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import websocket_api as console_ws
from .const import CONF_KEY_PATH, DOMAIN, PANEL_COMPONENT, PANEL_URL_PATH, STATIC_URL
from .ssh_session import ensure_key

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = hass.data.setdefault(DOMAIN, {})
    await hass.async_add_executor_job(ensure_key, entry.data[CONF_KEY_PATH])

    if not store.get("static_registered"):
        frontend_dir = str(Path(__file__).parent / "frontend")
        await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, frontend_dir, False)])
        console_ws.async_register(hass)
        store["static_registered"] = True

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{STATIC_URL}/panel.js?v=0.1.2",
        sidebar_title="Console",
        sidebar_icon="mdi:console",
        require_admin=True,
        config={},
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    await console_ws.async_close_all(hass)
    return True
