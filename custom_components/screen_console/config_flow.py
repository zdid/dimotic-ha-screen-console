"""Assistant d'ajout : machine locale, utilisateur, puis affichage de la ligne à autoriser côté machine."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_HOST,
    CONF_KEY_PATH,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
    GATE_SCRIPT_NAME,
    KEY_FILE_NAME,
    LOOPBACK_HOSTS,
)
from .ssh_session import authorized_keys_line, ensure_key


class ScreenConsoleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Une seule console par installation de HA."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._public_key = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_HOST] not in LOOPBACK_HOSTS:
                errors[CONF_HOST] = "not_local"
            else:
                key_path = self.hass.config.path(".storage", KEY_FILE_NAME)
                self._public_key = await self.hass.async_add_executor_job(ensure_key, key_path)
                self._data = {**user_input, CONF_KEY_PATH: key_path}
                return await self.async_step_key()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_key(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Screen Console", data=self._data)
        gate = f"/home/{self._data[CONF_USERNAME]}/bin/{GATE_SCRIPT_NAME}"
        return self.async_show_form(
            step_id="key",
            description_placeholders={
                "authorized_line": authorized_keys_line(self._public_key, gate),
                "gate_script": gate,
            },
        )
