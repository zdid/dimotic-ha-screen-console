"""Constantes de l'intégration Screen Console."""

DOMAIN = "screen_console"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_KEY_PATH = "key_path"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 22
DEFAULT_USERNAME = "claude"

# Hôtes acceptés : la console ne se connecte qu'à la machine qui héberge HA (pas de vérification
# de clé d'hôte, donc pas de connexion vers un autre ordinateur).
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

PANEL_URL_PATH = "screen-console"
PANEL_COMPONENT = "screen-console-panel"
STATIC_URL = "/screen_console_static"

# Nom d'un screen : lettres, chiffres, point, tiret, souligné (même règle que le script de contrôle).
SESSION_NAME_RE = r"^[A-Za-z0-9._-]{1,64}$"

MAX_SESSIONS = 3
KEY_FILE_NAME = "screen_console_ed25519"
KEY_COMMENT = "ha-screen-console"

# Nom du script de contrôle installé sur la machine hôte (voir README).
GATE_SCRIPT_NAME = "screen-console-gate"
