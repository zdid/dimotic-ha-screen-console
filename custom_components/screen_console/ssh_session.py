"""Connexion SSH locale vers la machine hôte et attachement à une session `screen`.

La clé SSH de l'intégration est restreinte côté hôte par un script de contrôle (voir README) :
elle ne peut que LISTER les sessions (`list`) ou S'ATTACHER à l'une d'elles (`attach <nom>`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import asyncssh

from .const import KEY_COMMENT, LOOPBACK_HOSTS, SESSION_NAME_RE

_LOGGER = logging.getLogger(__name__)

_SESSION_LINE = re.compile(r"^\s+(\d+)\.(\S+)\s+\(([^)]*)\)(?:\s+\(([^)]*)\))?")
CONNECT_TIMEOUT = 10
READ_CHUNK = 4096


@dataclass(frozen=True)
class SshTarget:
    """Où et comment se connecter."""

    host: str
    port: int
    username: str
    key_path: str

    def validate(self) -> None:
        if self.host not in LOOPBACK_HOSTS:
            raise ValueError("Seule la machine locale est acceptée (127.0.0.1, localhost ou ::1).")


def valid_session_name(name: str) -> bool:
    return re.fullmatch(SESSION_NAME_RE, name) is not None


def parse_screen_list(text: str) -> list[dict[str, str]]:
    """Analyse la sortie de `screen -ls` : [{'name': 'claude', 'pid': '98432', 'state': 'Detached'}…].

    La session `claude` passe en premier (demande utilisateur), les autres suivent par ordre alphabétique.
    """
    sessions: list[dict[str, str]] = []
    for line in text.splitlines():
        m = _SESSION_LINE.match(line)
        if not m:
            continue
        pid, name, first, second = m.groups()
        state = second or first
        sessions.append({"name": name, "pid": pid, "state": state})
    sessions.sort(key=lambda s: (s["name"] != "claude", s["name"].lower()))
    return sessions


def ensure_key(path: str) -> str:
    """Crée la paire de clés ed25519 si elle manque ; renvoie la clé publique (une ligne OpenSSH)."""
    key_file = Path(path)
    if not key_file.exists():
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key = asyncssh.generate_private_key("ssh-ed25519", comment=KEY_COMMENT)
        # Écriture en 0600 dès la création (pas de fenêtre où la clé serait lisible par d'autres).
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key.export_private_key())
        _LOGGER.info("Clé SSH de la console créée dans %s", path)
    return asyncssh.read_private_key(path).export_public_key().decode().strip()


def authorized_keys_line(public_key: str, gate_script: str) -> str:
    """Ligne à ajouter dans ~/.ssh/authorized_keys de l'utilisateur de la machine hôte."""
    options = (
        'from="127.0.0.1,::1",'
        f'command="{gate_script}",'
        "no-port-forwarding,no-X11-forwarding,no-agent-forwarding"
    )
    return f"{options} {public_key}"


async def _connect(target: SshTarget) -> asyncssh.SSHClientConnection:
    target.validate()
    return await asyncssh.connect(
        target.host,
        target.port,
        username=target.username,
        client_keys=[target.key_path],
        known_hosts=None,  # machine locale uniquement (voir SshTarget.validate)
        connect_timeout=CONNECT_TIMEOUT,
    )


async def list_sessions(target: SshTarget) -> list[dict[str, str]]:
    """Liste les sessions screen de la machine hôte."""
    async with await _connect(target) as conn:
        result = await conn.run("list", check=False, timeout=15)
    out = result.stdout if isinstance(result.stdout, str) else (result.stdout or b"").decode(errors="replace")
    return parse_screen_list(out)


OutputCallback = Callable[[bytes], Awaitable[None]]
CloseCallback = Callable[[str], Awaitable[None]]


class ScreenSession:
    """Une connexion SSH attachée à une session screen, avec pseudo-terminal."""

    def __init__(self, target: SshTarget, session_name: str) -> None:
        if not valid_session_name(session_name):
            raise ValueError("Nom de session invalide.")
        self._target = target
        self._name = session_name
        self._conn: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess | None = None
        self._reader: asyncio.Task | None = None
        self._closed = False

    async def start(self, cols: int, rows: int, on_output: OutputCallback, on_close: CloseCallback) -> None:
        self._conn = await _connect(self._target)
        self._process = await self._conn.create_process(
            f"attach {self._name}",
            term_type="xterm-256color",
            term_size=(max(cols, 10), max(rows, 3)),
            encoding=None,
        )
        self._reader = asyncio.create_task(self._pump(on_output, on_close))

    async def _pump(self, on_output: OutputCallback, on_close: CloseCallback) -> None:
        reason = "terminée"
        try:
            assert self._process is not None
            while True:
                data = await self._process.stdout.read(READ_CHUNK)
                if not data:
                    break
                await on_output(data)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - toute coupure réseau/SSH doit être signalée à l'écran
            reason = f"interrompue : {err}"
            _LOGGER.debug("Lecture SSH interrompue", exc_info=True)
        finally:
            if not self._closed:
                await self.close()
                await on_close(reason)

    async def write(self, data: bytes) -> None:
        if self._process is not None and not self._closed:
            self._process.stdin.write(data)

    async def resize(self, cols: int, rows: int) -> None:
        if self._process is not None and not self._closed:
            self._process.change_terminal_size(max(cols, 10), max(rows, 3))

    async def close(self) -> None:
        """Ferme la connexion SSH (la session screen reste ouverte, simplement détachée)."""
        if self._closed:
            return
        self._closed = True
        current = asyncio.current_task()
        if self._reader is not None and self._reader is not current:
            self._reader.cancel()
        if self._process is not None:
            self._process.close()
        if self._conn is not None:
            self._conn.close()
            try:
                await asyncio.wait_for(self._conn.wait_closed(), timeout=5)
            except (TimeoutError, asyncio.TimeoutError):
                _LOGGER.debug("Fermeture SSH trop longue, abandonnée")
