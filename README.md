# BOSSCORE MCP PACK

Paquet MCP modulaire de l’écosystème BOSS : WordPress, fichiers, Git,
déploiement, exécution contrôlée, santé et coordination multi-agents.
**Cross-platform Windows + Linux.**

## Principes

- **Inventaire dynamique** : 113 outils chargés avec le profil `full` au
  24 juillet 2026. Toujours vérifier avec `boss_tool_inventory`; ne pas figer
  ce total dans les procédures d’exploitation.
- **Profils composables** : `wordpress`, `files`, `full`.
- **Deux transports** : stdio pour les agents locaux et HTTP/SSE pour les
  connecteurs distants.
- **Moindre privilège** : scopes OAuth, claims PACTE, chemins et hôtes bornés.
- **Plans persistants** : les plans de déploiement sont stockés sur disque,
  associés à l’acteur OAuth et consommés une seule fois.
- **Aucun secret brut dans les plans** : l’acteur est identifié par sujet OAuth
  ou empreinte SHA-256 non réversible du jeton.

## Lancement — stdio

### Windows (PowerShell)

```powershell
$env:WORDPRESS_URL = "https://core.bosserpnext.com"
$env:WORDPRESS_USERNAME = "boss"
$env:WORDPRESS_APP_PASSWORD = "..."
$env:DEPLOY_TOKEN = "..."
$env:BOSSCORE_WORKSPACE = "H:\...\companies"
python.exe server.py
```

### Linux / VPS

```bash
export WORDPRESS_URL="https://core.bosserpnext.com"
export WORDPRESS_USERNAME="boss"
export WORDPRESS_APP_PASSWORD="..."
export DEPLOY_TOKEN="..."
export BOSSCORE_WORKSPACE="/home/bomoja/repos/companies"
python3 server.py
```

## Lancement — HTTP/SSE

```bash
source ~/repos/companies/.env
python3 server_http.py --host 127.0.0.1 --port 8765
```

Le connecteur public utilise `https://vps.bosserpnext.com/sse` derrière NGINX.
En production, activer `BOSSCORE_MCP_ENFORCE_AUTH=1`.

## Cycle de déploiement multi-agents

Le cycle supporté est :

```text
plan → redémarrage MCP → status → execute → verify
```

Conditions :

1. `BOSSCORE_MCP_STORE_DIR` doit pointer vers un répertoire persistant et
   accessible au compte de service.
2. `BOSSCORE_DEPLOY_PLAN_TTL` vaut 1800 secondes par défaut.
3. Le même acteur OAuth doit reprendre le plan après redémarrage.
4. Un autre acteur reçoit une erreur bornée et ne peut ni voir, ni exécuter,
   ni vérifier le plan.
5. Un mauvais `confirm_token` ne consomme pas le plan.

## Runbook de récupération

Après interruption ou redémarrage :

1. Vérifier le service et l’inventaire réel des outils.
2. Appeler `boss_deploy_status(plan_id=...)` avec le même connecteur OAuth.
3. Si le statut est `draft`, reprendre avec le `confirm_token` initial.
4. Si le statut est `success`, lancer `boss_deploy_verify`.
5. Si le plan est expiré, étranger ou introuvable, créer un nouveau plan.
6. Ne jamais copier le magasin de plans vers un autre acteur ni modifier son
   champ `actor`.
7. Si le fichier du magasin est illisible, conserver une copie de preuve,
   corriger les permissions, puis recréer le plan. Ne jamais injecter
   manuellement un plan dans le JSON.
8. Le redémarrage du service doit passer par l’unité systemd et le runbook
   administrateur; aucun contournement par processus parallèle.

## QA

```bash
python3 -m pytest
```

La suite ne dépend pas de chemins Windows externes ni de `pytest-asyncio`.

## Différences Windows / Linux

| Comportement | Windows | Linux |
|---|---|---|
| Tesseract OCR | chemin explicite possible | `tesseract` dans `PATH` |
| Workspace usuel | volume local | `/home/bomoja/repos/companies` |
| Séparateur `FILE_ROOTS` | `;` | `:` |
| Service HTTP | processus local | unité systemd derrière NGINX |
