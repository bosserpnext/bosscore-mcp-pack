"""Schemas des outils BOSSCORE MCP PACK - WordPress + Fichiers + Deploiement.
Chaque parametre a une description (obligatoire ChatGPT - "Unclear Arguments").
Chaque outputSchema a des descriptions sur ses proprietes (obligatoire - "Output schema recommended")."""

from mcp.types import Tool, ToolAnnotations

# -- Input schema primitives (reutilisables) -----------------------
_S = {
    "id":          {"type": "integer", "description": "Identifiant numerique unique de la ressource WordPress"},
    "title":       {"type": "string",  "description": "Titre de la ressource (page, article, bloc, menu, media)"},
    "content":     {"type": "string",  "description": "Contenu HTML ou texte brut de la ressource"},
    "status":      {"type": "string",  "enum": ["publish", "draft", "private", "pending", "future", "trash"], "description": "Statut de publication WordPress"},
    "slug":        {"type": "string",  "description": "Identifiant URL (slug) de la ressource"},
    "name":        {"type": "string",  "description": "Nom affiche ou identifiant textuel (utilisateur, categorie, tag, menu)"},
    "url":         {"type": "string",  "description": "URL complete (ex: URL d'une page, d'un lien de menu, d'une image)"},
    "email":       {"type": "string",  "format": "email", "description": "Adresse email valide"},
    "password":    {"type": "string",  "description": "Mot de passe (sera hache par WordPress)"},
    "username":    {"type": "string",  "description": "Nom d'utilisateur pour la connexion WordPress"},
    "meta":        {"type": "object",  "description": "Metadonnees personnalisees (paires cle-valeur libres)"},
    "settings":    {"type": "object",  "description": "Objet de configuration (theme Astra, reglages site)"},
    "menu_locations": {"type": "object", "description": "Dictionnaire associant des emplacements de menu a des IDs de menu"},
    "theme_mods":  {"type": "object",  "description": "Modifications du theme (theme_mods WordPress)"},
    "merge":       {"type": "boolean", "description": "Si true, fusionne avec les parametres existants. Si false, remplace tout."},
    "menu_id":     {"type": "integer", "description": "Identifiant numerique du menu de navigation"},
    "source_url":  {"type": "string",  "format": "uri", "description": "URL publique du fichier a telecharger dans la mediatheque"},
    "location":    {"type": "string",  "description": "Emplacement du menu dans le theme (ex: primary, secondary, mobile)"},
    "order":       {"type": "integer", "description": "Position dans l'ordre d'affichage (0 = premier)"},
    "endpoint":    {"type": "string",  "description": "Chemin API REST WordPress (ex: /wp/v2/pages) ou URL complete"},
    "method":      {"type": "string",  "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "description": "Methode HTTP pour la requete API"},
    "body":        {"type": "string",  "description": "Corps JSON de la requete API (pour POST/PUT)"},
    "post":        {"type": "integer", "description": "Identifiant de l'article auquel le commentaire est associe"},
    "parent":      {"type": "integer", "description": "Identifiant du commentaire parent (pour les reponses imbriquees)"},
    "author_name": {"type": "string",  "description": "Nom de l'auteur du commentaire"},
    "author_email":{"type": "string",  "format": "email", "description": "Email de l'auteur du commentaire"},
    "query":       {"type": "string",  "minLength": 1, "description": "Terme de recherche (texte libre, recherche plein texte WordPress)"},
    "per_page":    {"type": "integer", "minimum": 1, "maximum": 100, "description": "Nombre de resultats par page (max 100)"},
    "type":        {"type": "string",  "enum": ["post", "page", "attachment"], "description": "Type de contenu WordPress a rechercher"},
    "subtype":     {"type": "string",  "description": "Sous-type de contenu (ex: article, page) pour affiner la recherche"},
    "reassign":    {"type": "integer", "description": "ID de l'utilisateur a qui reassigner le contenu de l'utilisateur supprime"},
    "roles":       {"type": "array",   "items": {"type": "string"}, "description": "Liste des roles WordPress (ex: [\"administrator\", \"editor\"])"},
    "alt_text":    {"type": "string",  "description": "Texte alternatif pour l'accessibilite et le referencement des images"},
    "caption":     {"type": "string",  "description": "Legende affichee sous l'image dans WordPress"},
    "description": {"type": "string",  "description": "Texte descriptif (categorie, tag, site)"},
    "limit":       {"type": "integer", "minimum": 1, "description": "Nombre maximum d'elements a retourner ou de caracteres a lire"},
    "path":        {"type": "string",  "description": "Chemin absolu du fichier ou repertoire sur le serveur"},
    "pattern":     {"type": "string",  "minLength": 1, "description": "Motif de recherche (texte ou expression reguliere)"},
    "repo":        {"type": "string",  "enum": ["bosscore", "telet", "all"], "description": "Depot a deployer: bosscore (plugin WordPress), telet (theme), ou all (les deux)"},
    "key":         {"type": "string",  "description": "Cle de configuration Astra (ex: header-button1-text, transparent-header)"},
    "text":        {"type": "string",  "description": "Texte a afficher sur le bouton du header"},
    "button":      {"type": "string",  "enum": ["button-1", "button-2"], "description": "Identifiant du bouton Astra a configurer (button-1 ou button-2)"},
    "bg_color":    {"type": "string",  "pattern": "^#[0-9A-Fa-f]{6}$", "description": "Couleur de fond en hexadecimal (ex: #009FE3 pour le bleu BOSS)"},
    "text_color":  {"type": "string",  "pattern": "^#[0-9A-Fa-f]{6}$", "description": "Couleur du texte en hexadecimal (ex: #FFFFFF pour blanc)"},
    "bg_hover_color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$", "description": "Couleur de fond au survol en hexadecimal"},
    "radius":      {"type": "string",  "description": "Rayon de bordure du bouton (ex: 4px, 8px, 50%)"},
    "font_size":   {"type": "string",  "description": "Taille de police du bouton (ex: 14px, 1rem)"},
    "logged_out_text": {"type": "string", "description": "Texte du lien de connexion affiche aux utilisateurs non connectes"},
    "logged_in_text":  {"type": "string", "description": "Texte du lien de profil affiche aux utilisateurs connectes"},
    "login_url":   {"type": "string",  "description": "URL de la page de connexion"},
    "logout_url":  {"type": "string",  "description": "URL de deconnexion"},
    "login_style": {"type": "string",  "description": "Style CSS pour le lien de connexion"},
    "logout_style":{"type": "string",  "description": "Style CSS pour le lien de deconnexion"},
    "area":        {"type": "string",  "enum": ["desktop", "mobile"], "description": "Zone d'affichage: desktop (ordinateur) ou mobile (telephone)"},
    "section":     {"type": "string",  "enum": ["primary", "secondary", "tertiary"], "description": "Section du header: primary (principale), secondary (secondaire), tertiary (tertiaire)"},
    "slot":        {"type": "string",  "enum": ["primary_left", "primary_center", "primary_right", "secondary_left", "secondary_center", "secondary_right"], "description": "Emplacement dans la section: left (gauche), center (centre), right (droite)"},
    "items":       {"type": "array",   "items": {"type": "string"}, "description": "Liste des composants a placer dans le slot (ex: [\"button-1\", \"menu\"])"},
}

# -- Output schema fragments (reutilisables) ------------------------
_O = {
    "ok": {"type": "object", "properties": {
        "success": {"type": "boolean", "description": "True si l'operation a reussi, False sinon"},
        "message": {"type": "string", "description": "Message de confirmation ou d'erreur"},
    }},
    "created": {"type": "object", "properties": {
        "success": {"type": "boolean", "description": "True si la creation a reussi"},
        "id": {"type": "integer", "description": "Identifiant numerique de la ressource creee"},
    }},
    "list": {"type": "object", "properties": {
        "count": {"type": "integer", "description": "Nombre total d'elements dans la liste"},
        "items": {"type": "array", "description": "Tableau des elements (pages, articles, medias, etc.)"},
    }},
    "item": {"type": "object", "properties": {
        "id": {"type": "integer", "description": "Identifiant unique de la ressource"},
        "title": {"type": "string", "description": "Titre de la ressource"},
        "content": {"type": "string", "description": "Contenu HTML de la ressource"},
        "status": {"type": "string", "description": "Statut de publication (publish, draft, private, etc.)"},
        "meta": {"type": "object", "description": "Metadonnees personnalisees"},
    }},
    "user": {"type": "object", "properties": {
        "id": {"type": "integer", "description": "Identifiant unique de l'utilisateur"},
        "username": {"type": "string", "description": "Nom d'utilisateur (login)"},
        "name": {"type": "string", "description": "Nom affiche de l'utilisateur"},
        "email": {"type": "string", "description": "Adresse email de l'utilisateur"},
        "roles": {"type": "array", "items": {"type": "string"}, "description": "Roles WordPress assignes a l'utilisateur"},
    }},
    "media": {"type": "object", "properties": {
        "id": {"type": "integer", "description": "Identifiant unique du media"},
        "title": {"type": "string", "description": "Titre du media"},
        "url": {"type": "string", "description": "URL publique du fichier media"},
        "alt_text": {"type": "string", "description": "Texte alternatif pour l'accessibilite"},
        "mime_type": {"type": "string", "description": "Type MIME du fichier (ex: image/png, application/pdf)"},
    }},
    "menu": {"type": "object", "properties": {
        "id": {"type": "integer", "description": "Identifiant unique du menu"},
        "name": {"type": "string", "description": "Nom du menu"},
        "items": {"type": "array", "items": {"type": "object"}, "description": "Elements du menu (liens, pages, categories)"},
    }},
    "menu_locations": {"type": "object", "description": "Dictionnaire associant chaque emplacement de menu (cle) a l'ID du menu assigne (valeur)"},
    "settings": {"type": "object", "properties": {
        "title": {"type": "string", "description": "Titre du site WordPress"},
        "description": {"type": "string", "description": "Slogan ou description du site"},
        "timezone": {"type": "string", "description": "Fuseau horaire du site (ex: Europe/Paris)"},
        "url": {"type": "string", "description": "URL racine du site"},
    }},
    "site_info": {"type": "object", "properties": {
        "version": {"type": "string", "description": "Version de WordPress installee"},
        "namespaces": {"type": "array", "items": {"type": "string"}, "description": "Namespaces API REST disponibles"},
    }},
    "rest_index": {"type": "object", "properties": {
        "routes": {"type": "object", "description": "Routes disponibles dans l'API REST WordPress"},
    }},
    "themes": {"type": "object", "properties": {
        "active": {"type": "string", "description": "Nom du theme actif"},
        "available": {"type": "array", "items": {"type": "string"}, "description": "Liste des themes installes"},
    }},
    "astra_settings": {"type": "object", "properties": {
        "settings": {"type": "object", "description": "Configuration complete du theme Astra (header, footer, couleurs, typographie)"},
    }},
    "astra_header": {"type": "object", "properties": {
        "desktop": {"type": "object", "description": "Configuration des slots du header pour ordinateur"},
        "mobile": {"type": "object", "description": "Configuration des slots du header pour mobile"},
    }},
    "astra_setting": {"type": "object", "properties": {
        "key": {"type": "string", "description": "Nom du parametre Astra"},
        "value": {"description": "Valeur du parametre (type variable selon le parametre)"},
    }},
    "raw_api": {"type": "object", "properties": {
        "status": {"type": "integer", "description": "Code HTTP de la reponse (200, 201, 404, etc.)"},
        "body": {"description": "Corps de la reponse API (objet JSON, tableau, ou texte)"},
    }},
    "file_content": {"type": "object", "properties": {
        "content": {"type": "string", "description": "Contenu du fichier (texte, markdown, ou donnees extraites)"},
        "size": {"type": "integer", "description": "Taille du fichier en octets"},
        "type": {"type": "string", "description": "Type MIME detecte du fichier"},
    }},
    "file_image": {"type": "object", "properties": {
        "mime_type": {"type": "string", "description": "Type MIME de l'image (ex: image/png, image/jpeg)"},
        "data": {"type": "string", "description": "Donnees de l'image encodees en base64"},
    }},
    "file_list": {"type": "object", "properties": {
        "path": {"type": "string", "description": "Chemin absolu du repertoire liste"},
        "entries": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Nom du fichier ou dossier"},
            "type": {"type": "string", "enum": ["file", "directory"], "description": "Type: file (fichier) ou directory (dossier)"},
            "size": {"type": "integer", "description": "Taille en octets (0 pour les dossiers)"},
        }}, "description": "Liste des entrees du repertoire"},
    }},
    "file_info": {"type": "object", "properties": {
        "size": {"type": "integer", "description": "Taille du fichier en octets"},
        "type": {"type": "string", "description": "Type de fichier detecte"},
        "modified": {"type": "string", "description": "Date de derniere modification (timestamp Unix)"},
    }},
    "file_search": {"type": "object", "properties": {
        "count": {"type": "integer", "description": "Nombre total d'occurrences trouvees"},
        "matches": {"type": "array", "items": {"type": "string"}, "description": "Lignes ou extraits contenant le motif recherche"},
    }},
    "deploy": {"type": "object", "properties": {
        "success": {"type": "boolean", "description": "True si le deploiement a reussi"},
        "output": {"type": "string", "description": "Sortie des commandes git pull et rsync sur cPanel"},
    }},
    "git_push": {"type": "object", "properties": {
        "success": {"type": "boolean", "description": "True si le push Git a reussi (Linux) ou si la commande est prete (Windows)"},
        "output": {"type": "string", "description": "Sortie de git push (Linux) ou commande bash a executer manuellement (Windows)"},
    }},
    "comment": {"type": "object", "properties": {
        "id": {"type": "integer", "description": "Identifiant unique du commentaire"},
        "content": {"type": "string", "description": "Contenu texte du commentaire"},
        "author_name": {"type": "string", "description": "Nom de l'auteur du commentaire"},
        "status": {"type": "string", "description": "Statut du commentaire (approved, spam, trash)"},
    }},
}

# -- Tool annotations (obligatoire ChatGPT - jamais None/null) -----
_A = {
    "read":   ToolAnnotations(title="Read-only", readOnlyHint=True,  destructiveHint=False, idempotentHint=True,  openWorldHint=False),
    "write":  ToolAnnotations(title="Create/Update", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    "delete": ToolAnnotations(title="Delete (destructive)", readOnlyHint=False, destructiveHint=True,  idempotentHint=False, openWorldHint=False),
    "deploy": ToolAnnotations(title="Deploy", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    "git":    ToolAnnotations(title="Git push", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
}
R, W, D, P, G = _A["read"], _A["write"], _A["delete"], _A["deploy"], _A["git"]

# -- Construction de la liste d'outils ------------------------------
def tool_list() -> list[Tool]:
    return [
        # -- WORDPRESS PAGES --------------------------------------
        Tool(name="wp_list_pages",  description="List all WordPress pages", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_get_page",    description="Get a page by ID with content and meta", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["item"], annotations=R),
        Tool(name="wp_create_page", description="Create a new WordPress page", inputSchema={"type": "object", "properties": {"title": _S["title"], "content": _S["content"], "status": _S["status"]}, "required": ["title"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_update_page", description="Update a page: title, content, status, or meta", inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "content": _S["content"], "status": _S["status"], "meta": _S["meta"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_delete_page", description="Delete a page permanently", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=D),
        # -- WORDPRESS POSTS --------------------------------------
        Tool(name="wp_list_posts",  description="List WordPress blog posts", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_get_post",    description="Get a blog post by ID", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["item"], annotations=R),
        Tool(name="wp_create_post", description="Create a new blog post", inputSchema={"type": "object", "properties": {"title": _S["title"], "content": _S["content"], "status": _S["status"]}, "required": ["title"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_update_post", description="Update a blog post", inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "content": _S["content"], "status": _S["status"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_delete_post", description="Delete a blog post permanently", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=D),
        # -- WORDPRESS MEDIA --------------------------------------
        Tool(name="wp_list_media",  description="List media library items", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_get_media",   description="Get media item by ID with URLs", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["media"], annotations=R),
        Tool(name="wp_upload_media", description="Upload media from a public URL", inputSchema={"type": "object", "properties": {"source_url": _S["source_url"], "title": _S["title"]}, "required": ["source_url"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_update_media", description="Update media metadata (title, alt text, caption)", inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "alt_text": _S["alt_text"], "caption": _S["caption"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_delete_media", description="Delete a media item permanently", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=D),
        # -- WORDPRESS USERS --------------------------------------
        Tool(name="wp_list_users",  description="List users (may require elevated permissions)", inputSchema={"type": "object", "properties": {}}, outputSchema={"type": "object", "properties": {"items": {"type": "array", "items": _O["user"]["properties"], "description": "Liste des utilisateurs"}}}, annotations=R),
        Tool(name="wp_get_user",    description="Get user by ID", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["user"], annotations=R),
        Tool(name="wp_get_user_me", description="Get current authenticated user info", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["user"], annotations=R),
        Tool(name="wp_create_user", description="Create a new WordPress user", inputSchema={"type": "object", "properties": {"username": _S["username"], "password": _S["password"], "email": _S["email"]}, "required": ["username", "password"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_update_user", description="Update a user (name, email, password, roles)", inputSchema={"type": "object", "properties": {"id": _S["id"], "name": _S["name"], "email": _S["email"], "password": _S["password"], "roles": _S["roles"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_delete_user", description="Delete a user, reassigning content to another user", inputSchema={"type": "object", "properties": {"id": _S["id"], "reassign": _S["reassign"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=D),
        # -- WORDPRESS COMMENTS -----------------------------------
        Tool(name="wp_list_comments",  description="List recent comments, optionally filtered by post", inputSchema={"type": "object", "properties": {"post": _S["post"]}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_create_comment", description="Create a new comment on a post", inputSchema={"type": "object", "properties": {"post": _S["post"], "content": _S["content"], "author_name": _S["author_name"], "author_email": _S["author_email"], "parent": _S["parent"]}, "required": ["post", "content"]}, outputSchema=_O["comment"], annotations=W),
        Tool(name="wp_update_comment", description="Moderate a comment (approve/trash/spam)", inputSchema={"type": "object", "properties": {"id": _S["id"], "status": _S["status"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=W),
        # -- WORDPRESS TAXONOMIES ---------------------------------
        Tool(name="wp_list_categories",  description="List all categories", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_create_category",  description="Create a new category", inputSchema={"type": "object", "properties": {"name": _S["name"], "slug": _S["slug"], "description": _S["description"]}, "required": ["name"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_update_category",  description="Update a category name or description", inputSchema={"type": "object", "properties": {"id": _S["id"], "name": _S["name"], "slug": _S["slug"], "description": _S["description"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_delete_category",  description="Delete a category permanently", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=D),
        Tool(name="wp_list_tags",        description="List all tags", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_create_tag",       description="Create a new tag", inputSchema={"type": "object", "properties": {"name": _S["name"], "slug": _S["slug"], "description": _S["description"]}, "required": ["name"]}, outputSchema=_O["created"], annotations=W),
        # -- WORDPRESS MENUS --------------------------------------
        Tool(name="wp_list_menus",       description="List navigation menus", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_get_menu",         description="Get a navigation menu by ID", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["menu"], annotations=R),
        Tool(name="wp_create_menu",      description="Create a new navigation menu", inputSchema={"type": "object", "properties": {"name": _S["name"]}, "required": ["name"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_get_menu_items",   description="Get items for a menu", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema=_O["menu"], annotations=R),
        Tool(name="wp_create_menu_item", description="Add item to a menu", inputSchema={"type": "object", "properties": {"title": _S["title"], "url": _S["url"], "menu_id": _S["menu_id"], "order": _S["order"]}, "required": ["title", "url", "menu_id"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_get_menu_locations", description="Get all menu locations and their assigned menus", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["menu_locations"], annotations=R),
        # -- WORDPRESS SETTINGS -----------------------------------
        Tool(name="wp_get_settings",     description="Get site settings (title, description, timezone, etc.)", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["settings"], annotations=R),
        Tool(name="wp_update_settings",  description="Update site settings", inputSchema={"type": "object", "properties": {"title": _S["title"], "description": _S["description"], "timezone": _S["description"]}}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_get_site_info",    description="Get WordPress site info: version, routes, namespaces", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["site_info"], annotations=R),
        # -- WORDPRESS BLOCKS -------------------------------------
        Tool(name="wp_list_blocks",   description="List reusable blocks/patterns", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_get_block",     description="Get a reusable block by ID with content", inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]}, outputSchema={"type": "object", "properties": {"id": {"type": "integer", "description": "Identifiant du bloc"}, "title": {"type": "string", "description": "Titre du bloc"}, "content": {"type": "string", "description": "Contenu HTML du bloc"}}}, annotations=R),
        Tool(name="wp_create_block",  description="Create a reusable block", inputSchema={"type": "object", "properties": {"title": _S["title"], "content": _S["content"]}, "required": ["title", "content"]}, outputSchema=_O["created"], annotations=W),
        Tool(name="wp_update_block",  description="Update a reusable block content", inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "content": _S["content"]}, "required": ["id"]}, outputSchema=_O["ok"], annotations=W),
        # -- WORDPRESS SEARCH / THEMES ----------------------------
        Tool(name="wp_search",       description="Search posts, pages, and other content by query", inputSchema={"type": "object", "properties": {"query": _S["query"], "type": _S["type"], "subtype": _S["subtype"], "per_page": _S["per_page"]}, "required": ["query"]}, outputSchema=_O["list"], annotations=R),
        Tool(name="wp_list_themes",  description="List themes (active + available)", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["themes"], annotations=R),
        # -- ASTRA ------------------------------------------------
        Tool(name="wp_astra_get_settings",     description="Get all Astra theme settings (header, footer, colors, typography)", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["astra_settings"], annotations=R),
        Tool(name="wp_astra_update_settings",  description="Update Astra theme settings. Use merge=true (default) to merge, false to replace.", inputSchema={"type": "object", "properties": {"settings": _S["settings"], "merge": _S["merge"], "menu_locations": _S["menu_locations"], "theme_mods": _S["theme_mods"]}, "required": ["settings"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_astra_set_menu_location", description="Assign a menu to an Astra header/footer location", inputSchema={"type": "object", "properties": {"menu_id": _S["id"], "location": _S["location"]}, "required": ["menu_id", "location"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_astra_get_setting",       description="Get a single Astra setting by key name (e.g. header-button1-text)", inputSchema={"type": "object", "properties": {"key": _S["key"]}, "required": ["key"]}, outputSchema=_O["astra_setting"], annotations=R),
        Tool(name="wp_astra_get_header_builder", description="Get the current header builder layout - slot assignments for desktop and mobile", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["astra_header"], annotations=R),
        Tool(name="wp_astra_set_header_item",   description='Set component(s) in a header slot. e.g. area=desktop, section=primary, slot=primary_right, items=["button-1"]', inputSchema={"type": "object", "properties": {"area": _S["area"], "section": _S["section"], "slot": _S["slot"], "items": _S["items"]}, "required": ["area", "section", "slot", "items"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_astra_configure_button",  description="Batch-configure a header button: text, link, colors, radius, size.", inputSchema={"type": "object", "properties": {"button": _S["button"], "text": _S["text"], "url": _S["url"], "bg_color": _S["bg_color"], "text_color": _S["text_color"], "bg_hover_color": _S["bg_hover_color"], "radius": _S["radius"], "font_size": _S["font_size"]}, "required": ["button"]}, outputSchema=_O["ok"], annotations=W),
        Tool(name="wp_astra_configure_account", description="Configure the Astra account widget - shows login link when logged out, profile link when logged in.", inputSchema={"type": "object", "properties": {"logged_out_text": _S["logged_out_text"], "logged_in_text": _S["logged_in_text"], "login_url": _S["login_url"], "logout_url": _S["logout_url"], "login_style": _S["login_style"], "logout_style": _S["logout_style"]}}, outputSchema=_O["ok"], annotations=W),
        # -- WORDPRESS UTILITY ------------------------------------
        Tool(name="wp_raw_request",   description="Make any authenticated WP REST API request. endpoint=/wp/v2/pages or full URL", inputSchema={"type": "object", "properties": {"endpoint": _S["endpoint"], "method": _S["method"], "body": _S["body"]}, "required": ["endpoint"]}, outputSchema=_O["raw_api"], annotations=W),
        Tool(name="wp_get_rest_index", description="Get the WP REST API index (all available routes)", inputSchema={"type": "object", "properties": {}}, outputSchema=_O["rest_index"], annotations=R),

        # -- FILE READER ------------------------------------------
        Tool(name="file_reader_read_file", description="Read any file: PDF, DOCX, PPTX, XLSX, images, audio, text, CSV, HTML, Markdown. Auto-detect format.", inputSchema={"type": "object", "properties": {"path": _S["path"], "limit": _S["limit"]}, "required": ["path"]}, outputSchema=_O["file_content"], annotations=R),
        Tool(name="file_reader_read_image", description="Read an image file and return base64 data with MIME type", inputSchema={"type": "object", "properties": {"path": _S["path"]}, "required": ["path"]}, outputSchema=_O["file_image"], annotations=R),
        Tool(name="file_reader_convert_to_markdown", description="Convert any document (PDF, DOCX, PPTX, XLSX, HTML) to clean markdown text", inputSchema={"type": "object", "properties": {"path": _S["path"], "limit": _S["limit"]}, "required": ["path"]}, outputSchema=_O["file_content"], annotations=R),
        Tool(name="file_reader_list_directory", description="List files and subdirectories in a directory", inputSchema={"type": "object", "properties": {"path": _S["path"], "limit": _S["limit"]}, "required": ["path"]}, outputSchema=_O["file_list"], annotations=R),
        Tool(name="file_reader_get_file_info", description="Get metadata about a file (size, type, modified date)", inputSchema={"type": "object", "properties": {"path": _S["path"]}, "required": ["path"]}, outputSchema=_O["file_info"], annotations=R),
        Tool(name="file_reader_search_in_file", description="Search for a pattern in a file's content (supports PDF, DOCX, etc.)", inputSchema={"type": "object", "properties": {"path": _S["path"], "pattern": _S["pattern"], "limit": _S["limit"]}, "required": ["path", "pattern"]}, outputSchema=_O["file_search"], annotations=R),

        # -- cPanel DEPLOY ----------------------------------------
        Tool(name="boss_deploy",  description="Deploie le code BOSS sur cPanel (git pull + rsync). repo: bosscore (plugin), telet (theme), ou all (les deux).", inputSchema={"type": "object", "properties": {"repo": _S["repo"]}, "required": ["repo"]}, outputSchema=_O["deploy"], annotations=P),

        # -- GIT VERSION CONTROL ----------------------------------
        Tool(name="boss_git_push", description="Git add + commit + push. message: commit message obligatoire. Sur Windows retourne la commande bash a executer manuellement.", inputSchema={"type": "object", "properties": {"message": {"type": "string", "minLength": 1, "description": "Message de commit descriptif pour git"}}, "required": ["message"]}, outputSchema=_O["git_push"], annotations=G),
    ]
