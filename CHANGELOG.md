# Changelog

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

