"""Tests des fonctions pures de l'intégration (sans connexion SSH)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

from screen_console.ssh_session import (  # noqa: E402
    authorized_keys_line,
    parse_screen_list,
    valid_session_name,
)

SORTIE = """There are screens on:
\t561824.sc_test\t(10/12/26 15:07:05)\t(Detached)
\t98432.claude\t(10/07/26 19:50:18)\t(Attached)
\t7.Zed\t(10/07/26 19:50:18)\t(Detached)
2 Sockets in /run/screen/S-claude.
"""


def test_la_session_claude_vient_en_premier():
    noms = [s["name"] for s in parse_screen_list(SORTIE)]
    assert noms == ["claude", "sc_test", "Zed"]


def test_etat_et_pid():
    claude = parse_screen_list(SORTIE)[0]
    assert (claude["pid"], claude["state"]) == ("98432", "Attached")


def test_aucune_session():
    assert parse_screen_list("No Sockets found in /run/screen/S-claude.\n") == []


def test_noms_de_session():
    assert valid_session_name("claude") and valid_session_name("a.b_c-1")
    for mauvais in ("", "../etc/passwd", "a b", "a;b", "x" * 65, "a\nb"):
        assert not valid_session_name(mauvais)


def test_ligne_authorized_keys_restreinte():
    ligne = authorized_keys_line("ssh-ed25519 AAAA clé", "/home/claude/bin/screen-console-gate")
    assert ligne.startswith('from="127.0.0.1,::1",command="/home/claude/bin/screen-console-gate",')
    for option in ("no-port-forwarding", "no-X11-forwarding", "no-agent-forwarding"):
        assert option in ligne
    assert "no-pty" not in ligne  # le terminal est indispensable
    assert ligne.endswith("ssh-ed25519 AAAA clé")
