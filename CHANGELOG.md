# Changelog

## 0.4.1 — 2026-07-24

- Propagation de l’identité et des scopes OAuth vers `RequestContext`.
- Réinitialisation systématique du contexte après chaque requête HTTP.
- Propriété des plans de déploiement appliquée à `status`, `execute`,
  `verify` et `rollback`.
- Persistance validée à travers une recréation du provider et du magasin.
- Un mauvais jeton de confirmation ne consomme plus le plan.
- TTL de déploiement configurable, 1800 secondes par défaut.
- Scopes de staging et production revalidés selon l’environnement du plan.
- Tests multi-agents, cross-agent et runbook de récupération ajoutés.
- Tests rendus portables Linux/Windows, sans dépendance à des fichiers locaux
  historiques ni à `pytest-asyncio`.
- Inventaire documentaire corrigé : 113 outils pour le profil `full` au
  moment de l’audit, à vérifier dynamiquement.
- QA : 37 tests réussis.

## 0.1.0 — 2026-07-17

- Création du paquet modulaire BOSSCORE MCP.
- Ajout des profils `wordpress`, `files` et `full`.
- Conservation des 55 noms d’outils WordPress et des 6 noms d’outils
  documentaires historiques.
- Séparation du registre MCP, des services, des clients et des politiques.
- Ajout des annotations de lecture, destruction, idempotence et monde ouvert.
- Interdiction des URL absolues dans `wp_raw_request`.
- Protection du téléchargement média contre SSRF, redirections dangereuses et
  dépassements de taille.
- Ajout d’une liste blanche de racines pour les fichiers locaux.
- Interdiction permanente des chemins `credentials`, `_/zip`, `.ssh`, `.aws`
  et `.gnupg`.
- Chargement paresseux de MarkItDown, Pillow, Tesseract et Whisper.
- Ajout de 16 tests de contrat, de sécurité et de lecture documentaire.
