# BOSSCORE MCP PACK

Paquet modulaire de capacités MCP pour l’écosystème BOSS. Il absorbe
progressivement les anciens serveurs monofichiers `mcp-wordpress-bridge.py` et
`mcp-file-reader.py` sans coupler l’intelligence réutilisable au protocole MCP.

## Principes

- **Un paquet, plusieurs profils** : `wordpress`, `files` et `full`.
- **MCP reste une façade** : clients, extracteurs et politiques sont importables
  par un worker, une API ou un autre paquet.
- **Moindre privilège** : les chemins locaux et les hôtes distants sont bornés.
- **Dépendances paresseuses** : OCR, vision et transcription ne sont chargés
  que lorsqu’un outil les demande.
- **Contrats stables** : les 61 noms d’outils historiques sont conservés pendant
  la migration.

## Lancement

```powershell
$env:BOSSCORE_MCP_PROFILE = "wordpress"
$env:WORDPRESS_URL = "https://example.com"
$env:WORDPRESS_USERNAME = "..."
$env:WORDPRESS_APP_PASSWORD = "..."
python.exe C:\Users\Takoudjou\.config\opencode\bosscore-mcp-pack\server.py
```

Pour le lecteur de fichiers, les racines sont obligatoires :

```powershell
$env:BOSSCORE_MCP_PROFILE = "files"
$env:BOSSCORE_FILE_ROOTS = "H:\Documents;C:\Users\Takoudjou\Downloads"
python.exe C:\Users\Takoudjou\.config\opencode\bosscore-mcp-pack\server.py
```

Les dossiers nommés `credentials` et les chemins `_\zip` restent interdits,
même lorsqu’ils se trouvent sous une racine autorisée.

## Profils

| Profil | Capacités |
|---|---|
| `wordpress` | REST WordPress, BOSSCORE/Astra |
| `files` | lecture et extraction documentaire locale |
| `full` | réunion explicite des deux profils |

`wp_raw_request` n’accepte plus d’URL absolue. `wp_upload_media` refuse les
adresses privées, locales ou réservées afin d’empêcher les requêtes réseau
internes involontaires.

