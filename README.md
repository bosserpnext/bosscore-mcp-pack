# BOSSCORE MCP PACK

Paquet modulaire de capacités MCP pour l'écosystème BOSS — WordPress, fichiers,
déploiement cPanel. **Cross-platform Windows + Linux.**

## Principes

- **63 outils** : 55 WordPress/Astra + 6 File Reader + 2 BOSS (`boss_git_push`, `boss_deploy`)
- **Un paquet, plusieurs profils** : `wordpress`, `files`, `full`
- **Deux modes de transport** : stdio (OpenCode/Codex/Claude) + HTTP/SSE (chatgpt.com)
- **Cross-platform** : détection auto de l'OS, chemins adaptés, Tesseract Linux/Windows
- **Moindre privilège** : chemins locaux et hôtes distants bornés

## Lancement — stdio (OpenCode, Codex, Claude Desktop)

### Windows (PowerShell)
```powershell
$env:WORDPRESS_URL = "https://core.bosserpnext.com"
$env:WORDPRESS_USERNAME = "boss"
$env:WORDPRESS_APP_PASSWORD = "..."
$env:DEPLOY_TOKEN = "..."
$env:BOSSCORE_WORKSPACE = "H:\...\in-infrastructure-management"
python.exe server.py
```

### Linux / VPS (bash)
```bash
export WORDPRESS_URL="https://core.bosserpnext.com"
export WORDPRESS_USERNAME="boss"
export WORDPRESS_APP_PASSWORD="..."
export DEPLOY_TOKEN="..."
export BOSSCORE_WORKSPACE="/home/bomoja/repos/companies"
python3 server.py
```

## Lancement — HTTP/SSE (chatgpt.com)

```bash
# Sur le VPS
source ~/repos/companies/.env
python3 server_http.py --host 127.0.0.1 --port 8765

# Puis configurer chatgpt.com :
# Settings → Apps & Connectors → Add custom connector
# URL: https://vps.bosserpnext.com/sse  (via proxy NGINX)
# ou:  http://VPS_IP:8765/sse            (via tunnel SSH)
```

## Différences Windows / Linux

| Comportement | Windows | Linux |
|---|---|---|
| `boss_git_push` | Retourne commande bash | Exécute git directement (subprocess) |
| Tesseract OCR | `C:\Program Files\Tesseract-OCR\tesseract.exe` | `tesseract` dans PATH |
| Workspace par défaut | `H:\...\in-infrastructure-management` | `~/repos/companies` |
| Séparateur FILE_ROOTS | `;` | `:` |
