# Dimotic-HA Screen Console

Une **console `screen` dans Home Assistant** : un panneau « Console » dans le menu de gauche, qui affiche
une session `screen` de la machine qui héberge Home Assistant — sur ordinateur comme dans l'application
mobile HA (Android et iOS : même moteur web, voir « Limites »).

- **Aucun autre service à exposer.** Tout passe par la connexion WebSocket de HA : l'accès est celui de HA
  (réservé aux **administrateurs**), y compris à distance si vous utilisez déjà HA ainsi.
- **Choix de la session** dans une liste (la session `claude` est proposée en premier).
- **Barre de touches** pour le téléphone : Défiler (Ctrl-A puis Échap, mode copie de `screen`), ↑ ↓, Page ↑/↓, Échap, Tab, Ctrl-C.
- **Souris** : par défaut aucun mouvement, clic ni coup de molette n'est envoyé au programme distant (sinon des restes de séquences, par ex. `60;46m`,
  s'inscrivent dans la saisie) ; la molette fait défiler l'historique local. Le bouton **« Souris : non/oui »** de la barre envoie les clics et la molette
  (les mouvements restent toujours filtrés).
- Connexion **SSH locale uniquement** (127.0.0.1) avec une **clé restreinte** : elle ne peut que *lister* les sessions
  et *s'attacher* à l'une d'elles.

> ⚠️ Cette console donne un shell sur la machine (celui de l'utilisateur choisi). Elle est réservée aux administrateurs
> de HA, mais traitez-la comme un accès sensible.

## Installation

1. **HACS** → menu ⋮ → *Dépôts personnalisés* → ajouter `https://github.com/zdid/dimotic-ha-screen-console`,
   type *Intégration* → télécharger → **redémarrer Home Assistant**.
2. **Paramètres → Appareils et services → Ajouter une intégration → « Screen console »**. Renseigner l'utilisateur de la
   machine qui possède les sessions `screen` (adresse `127.0.0.1`, port 22).
3. L'assistant crée une clé SSH (`.storage/screen_console_ed25519` dans la configuration de HA) et affiche **la ligne à
   ajouter dans `~/.ssh/authorized_keys`** de cet utilisateur.
4. Sur la machine, installer le **script de contrôle** [`host/screen-console-gate`](host/screen-console-gate) :

   ```bash
   mkdir -p ~/bin
   curl -fsSL https://raw.githubusercontent.com/zdid/dimotic-ha-screen-console/main/host/screen-console-gate -o ~/bin/screen-console-gate
   chmod 755 ~/bin/screen-console-gate
   ```

   puis ajouter la ligne affichée par l'assistant à `~/.ssh/authorized_keys` (elle ressemble à :
   `from="127.0.0.1,::1",command="/home/UTILISATEUR/bin/screen-console-gate",no-port-forwarding,no-X11-forwarding,no-agent-forwarding ssh-ed25519 AAAA… ha-screen-console`).

Le panneau **Console** apparaît alors dans le menu (pour les administrateurs).

## Sécurité

- La clé n'est acceptée **que depuis 127.0.0.1 / ::1** et n'exécute **que** le script de contrôle, qui n'accepte que
  `list` et `attach <nom>` (nom : lettres, chiffres, `.`, `_`, `-`). Pas de redirection de port, ni d'X11, ni d'agent.
- Les commandes WebSocket de la console sont réservées aux administrateurs ; une session n'est utilisable que par la
  connexion WebSocket qui l'a ouverte ; 3 sessions simultanées au maximum.
- L'intégration refuse toute adresse autre que la machine locale (la clé d'hôte n'est pas vérifiée).
- Fermer la page détache simplement `screen` : la session et ses programmes continuent de tourner.

## Limites

- **Vérifié** (HA 2026.8 en conteneur) : génération de la clé, liste des sessions, attachement, saisie, redimensionnement, refus des ordres
  et des noms non autorisés, fonctions pures. Le panneau s'affiche et se connecte dans un navigateur de bureau (vérifié le 12/10/2026). **Pas encore vérifié** : l'application mobile HA.
  Sur Android et iOS le panneau est une page web standard (même moteur que l'application HA) donc il devrait fonctionner, mais le clavier
  virtuel du téléphone a ses particularités (Ctrl, Échap, flèches : d'où la barre de touches). **iOS : non testé.**
- Une seule machine (locale) ; HA doit pouvoir joindre `127.0.0.1:22` (HA en conteneur avec `network_mode: host`, ou HA OS/Supervised
  avec accès SSH local).
- Dépend de `asyncssh` (installé automatiquement par HA).

## Développement

`python3 -m pytest tests` (fonctions pures). La partie SSH/`screen` se vérifie sur une vraie machine.

Terminal : [xterm.js](https://github.com/xtermjs/xterm.js) (licence MIT, fichier `XTERM_LICENSE.txt`). Licence du dépôt : MIT.
