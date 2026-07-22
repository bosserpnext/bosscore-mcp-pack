# Architecture

## Principe

`bosscore-mcp-pack` est une distribution de capacités, pas un monolithe MCP.
Les services réutilisables ignorent le protocole ; les providers ne font que
déclarer leurs contrats dans le registre.

```text
Transport MCP
    ↓
ToolRegistry + profils
    ↓
Providers WordPress / Documents
    ↓
Services, clients et politiques réutilisables
    ↓
WordPress REST, système de fichiers, Ollama, OCR, STT
```

## Profils

- `wordpress` : expose uniquement la surface distante WordPress/BOSSCORE.
- `files` : expose uniquement la lecture documentaire locale bornée.
- `full` : compose explicitement les deux surfaces.

Le paquet peut donc être partagé sans obliger chaque client à recevoir 61 outils
ni à accorder simultanément des droits réseau et des droits fichiers.

## Extension future

Une nouvelle capacité doit fournir des `ToolSpec` et placer sa logique hors MCP.
Si elle est générique, elle vit dans un service réutilisable. Si elle est propre
à une activité, elle reste dans un adaptateur métier comme SMARTSHOP.

Le rapprochement futur avec `csgmcppack` devra se faire par extraction de
bibliothèques génériques ou par providers, jamais par copie divergente de
modules.

