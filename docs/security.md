# Politique de sécurité

## WordPress

- Une requête authentifiée ne peut viser que le `WORDPRESS_URL` configuré.
- `wp_raw_request` exige un chemin relatif `/wp-json/...`.
- Les téléchargements média n’envoient aucune authentification WordPress.
- Chaque URL et chaque redirection média sont résolues puis refusées si elles
  pointent vers une adresse privée, locale, réservée ou multicast.
- La taille maximale d’un média distant est de 25 Mio.
- Les outils destructifs et sensibles sont annotés dans leur contrat MCP.

## Fichiers

- `BOSSCORE_FILE_ROOTS` est obligatoire pour les profils `files` et `full`.
- Seuls les chemins absolus dont la résolution canonique reste dans une racine
  autorisée sont acceptés.
- Les liens symboliques ne permettent pas de sortir d’une racine.
- `credentials`, `_/zip`, `.ssh`, `.aws` et `.gnupg` sont toujours interdits.
- La taille maximale par défaut est de 100 Mio et peut être réduite par
  `BOSSCORE_MAX_FILE_BYTES`.
- La quantité de texte retournée est bornée par
  `BOSSCORE_MAX_OUTPUT_CHARS`.

## Secrets

Le paquet ne contient aucun secret. Les identifiants sont injectés par
environnement. Ils ne doivent pas être consignés dans le dépôt, les mémoires
agents ou les journaux.

