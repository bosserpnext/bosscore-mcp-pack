"""Schémas des outils BOSSCORE MCP PACK — WordPress + Fichiers + Déploiement.
Tous les outils incluent inputSchema ET outputSchema pour que le LLM comprenne
la forme des résultats attendus (recommandé par les guidelines MCP)."""

from mcp.types import Tool

# ── Input schema primitives (réutilisables) ─────────────────────
_S = {
    "id":          {"type": "integer"},
    "title":       {"type": "string"},
    "content":     {"type": "string"},
    "status":      {"type": "string"},
    "slug":        {"type": "string"},
    "name":        {"type": "string"},
    "url":         {"type": "string"},
    "email":       {"type": "string"},
    "password":    {"type": "string"},
    "username":    {"type": "string"},
    "meta":        {"type": "object"},
    "settings":    {"type": "object"},
    "menu_locations": {"type": "object"},
    "theme_mods":  {"type": "object"},
    "merge":       {"type": "boolean"},
    "menu_id":     {"type": "integer"},
    "source_url":  {"type": "string"},
    "location":    {"type": "string"},
    "order":       {"type": "integer"},
    "endpoint":    {"type": "string"},
    "method":      {"type": "string"},
    "body":        {"type": "string"},
    "post":        {"type": "integer"},
    "parent":      {"type": "integer"},
    "author_name": {"type": "string"},
    "author_email":{"type": "string"},
    "query":       {"type": "string"},
    "per_page":    {"type": "integer"},
    "type":        {"type": "string"},
    "subtype":     {"type": "string"},
    "reassign":    {"type": "integer"},
    "roles":       {"type": "array"},
    "alt_text":    {"type": "string"},
    "caption":     {"type": "string"},
    "description": {"type": "string"},
    "limit":       {"type": "integer"},
    "path":        {"type": "string"},
    "pattern":     {"type": "string"},
    "repo":        {"type": "string"},
    "key":         {"type": "string"},
    "text":        {"type": "string"},
    "button":      {"type": "string"},
    "bg_color":    {"type": "string"},
    "text_color":  {"type": "string"},
    "bg_hover_color": {"type": "string"},
    "radius":      {"type": "string"},
    "font_size":   {"type": "string"},
    "logged_out_text": {"type": "string"},
    "logged_in_text":  {"type": "string"},
    "login_url":   {"type": "string"},
    "logout_url":  {"type": "string"},
    "login_style": {"type": "string"},
    "logout_style":{"type": "string"},
    "area":        {"type": "string"},
    "section":     {"type": "string"},
    "slot":        {"type": "string"},
    "items":       {"type": "array", "items": {"type": "string"}},
}

# ── Output schema fragments (réutilisables) ──────────────────────
_O = {
    # Confirmation simple (success/failure)
    "ok": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "message": {"type": "string", "description": "Message de confirmation"},
        },
    },
    # Création/update : retourne l'ID
    "created": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "id": {"type": "integer", "description": "ID de l'élément créé ou modifié"},
        },
    },
    # Liste paginée
    "list": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Nombre total d'éléments"},
            "items": {"type": "array", "description": "Liste des éléments"},
        },
    },
    # Élément unique (page/post/media/block/catégorie/tag/commentaire)
    "item": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "status": {"type": "string"},
            "meta": {"type": "object"},
        },
    },
    # Utilisateur
    "user": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "username": {"type": "string"},
            "name": {"type": "string"},
            "email": {"type": "string"},
            "roles": {"type": "array", "items": {"type": "string"}},
        },
    },
    # Média
    "media": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "title": {"type": "string"},
            "url": {"type": "string", "description": "URL publique du média"},
            "alt_text": {"type": "string"},
            "mime_type": {"type": "string"},
        },
    },
    # Menu de navigation
    "menu": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object"}},
        },
    },
    # Menu locations (assignations emplacement → menu)
    "menu_locations": {
        "type": "object",
        "description": "Dictionnaire clé=emplacement, valeur=ID du menu",
    },
    # Site settings
    "settings": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "timezone": {"type": "string"},
            "url": {"type": "string"},
        },
    },
    # Site info
    "site_info": {
        "type": "object",
        "properties": {
            "version": {"type": "string", "description": "Version WordPress"},
            "namespaces": {"type": "array", "items": {"type": "string"}},
        },
    },
    # REST index
    "rest_index": {
        "type": "object",
        "properties": {
            "routes": {"type": "object", "description": "Routes disponibles dans l'API REST"},
        },
    },
    # Thèmes
    "themes": {
        "type": "object",
        "properties": {
            "active": {"type": "string", "description": "Thème actif"},
            "available": {"type": "array", "items": {"type": "string"}},
        },
    },
    # Astra settings
    "astra_settings": {
        "type": "object",
        "properties": {
            "settings": {"type": "object", "description": "Configuration complète du thème Astra"},
        },
    },
    # Astra header builder
    "astra_header": {
        "type": "object",
        "properties": {
            "desktop": {"type": "object", "description": "Slots header desktop"},
            "mobile": {"type": "object", "description": "Slots header mobile"},
        },
    },
    # Astra setting simple (key → value)
    "astra_setting": {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"description": "Valeur du paramètre (type variable)"},
        },
    },
    # Raw WP API request
    "raw_api": {
        "type": "object",
        "properties": {
            "status": {"type": "integer", "description": "Code HTTP de la réponse"},
            "body": {"description": "Corps JSON de la réponse (type variable)"},
        },
    },
    # Fichier (contenu texte/markdown)
    "file_content": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Contenu du fichier (texte ou markdown)"},
            "size": {"type": "integer", "description": "Taille en octets"},
            "type": {"type": "string", "description": "Type MIME détecté"},
        },
    },
    # Fichier image (base64)
    "file_image": {
        "type": "object",
        "properties": {
            "mime_type": {"type": "string", "description": "Type MIME (ex: image/png)"},
            "data": {"type": "string", "description": "Données encodées en base64"},
        },
    },
    # Liste de fichiers / répertoire
    "file_list": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin du répertoire listé"},
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["file", "directory"]},
                        "size": {"type": "integer"},
                    },
                },
            },
        },
    },
    # Métadonnées d'un fichier
    "file_info": {
        "type": "object",
        "properties": {
            "size": {"type": "integer"},
            "type": {"type": "string"},
            "modified": {"type": "string", "description": "Date de dernière modification (ISO 8601)"},
        },
    },
    # Résultat de recherche dans un fichier
    "file_search": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Nombre d'occurrences trouvées"},
            "matches": {"type": "array", "items": {"type": "string"}},
        },
    },
    # Déploiement
    "deploy": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "output": {"type": "string", "description": "Sortie des commandes git pull + rsync"},
        },
    },
    # Git push
    "git_push": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "output": {"type": "string", "description": "Sortie de git push, ou commande bash à exécuter (Windows)"},
        },
    },
    # Comment
    "comment": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "content": {"type": "string"},
            "author_name": {"type": "string"},
            "status": {"type": "string"},
        },
    },
}

# ── Construction de la liste d'outils ────────────────────────────
def tool_list() -> list[Tool]:
    return [
        # ── WORDPRESS PAGES ──────────────────────────────────────
        Tool(name="wp_list_pages", description="List all WordPress pages",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["list"]),
        Tool(name="wp_get_page", description="Get a page by ID with content and meta",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["item"]),
        Tool(name="wp_create_page", description="Create a new WordPress page",
             inputSchema={"type": "object", "properties": {"title": _S["title"], "content": _S["content"], "status": _S["status"]}, "required": ["title"]},
             outputSchema=_O["created"]),
        Tool(name="wp_update_page", description="Update a page: title, content, status, or meta",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "content": _S["content"], "status": _S["status"], "meta": _S["meta"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_delete_page", description="Delete a page permanently",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        # ── WORDPRESS POSTS ──────────────────────────────────────
        Tool(name="wp_list_posts", description="List WordPress blog posts",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["list"]),
        Tool(name="wp_get_post", description="Get a blog post by ID",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["item"]),
        Tool(name="wp_create_post", description="Create a new blog post",
             inputSchema={"type": "object", "properties": {"title": _S["title"], "content": _S["content"], "status": _S["status"]}, "required": ["title"]},
             outputSchema=_O["created"]),
        Tool(name="wp_update_post", description="Update a blog post",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "content": _S["content"], "status": _S["status"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_delete_post", description="Delete a blog post permanently",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        # ── WORDPRESS MEDIA ──────────────────────────────────────
        Tool(name="wp_list_media", description="List media library items",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["list"]),
        Tool(name="wp_get_media", description="Get media item by ID with URLs",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["media"]),
        Tool(name="wp_upload_media", description="Upload media from a public URL",
             inputSchema={"type": "object", "properties": {"source_url": _S["source_url"], "title": _S["title"]}, "required": ["source_url"]},
             outputSchema=_O["created"]),
        Tool(name="wp_update_media", description="Update media metadata (title, alt text, caption)",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "alt_text": _S["alt_text"], "caption": _S["caption"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_delete_media", description="Delete a media item permanently",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        # ── WORDPRESS USERS ──────────────────────────────────────
        Tool(name="wp_list_users", description="List users (may require elevated permissions)",
             inputSchema={"type": "object", "properties": {}},
             outputSchema={"type": "object", "properties": {"items": {"type": "array", "items": _O["user"]["properties"]}}}),
        Tool(name="wp_get_user", description="Get user by ID",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["user"]),
        Tool(name="wp_get_user_me", description="Get current authenticated user info",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["user"]),
        Tool(name="wp_create_user", description="Create a new WordPress user",
             inputSchema={"type": "object", "properties": {"username": _S["username"], "password": _S["password"], "email": _S["email"]}, "required": ["username", "password"]},
             outputSchema=_O["created"]),
        Tool(name="wp_update_user", description="Update a user (name, email, password, roles)",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "name": _S["name"], "email": _S["email"], "password": _S["password"], "roles": _S["roles"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_delete_user", description="Delete a user, reassigning content to another user",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "reassign": _S["reassign"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        # ── WORDPRESS COMMENTS ───────────────────────────────────
        Tool(name="wp_list_comments", description="List recent comments, optionally filtered by post",
             inputSchema={"type": "object", "properties": {"post": _S["post"]}},
             outputSchema=_O["list"]),
        Tool(name="wp_create_comment", description="Create a new comment on a post",
             inputSchema={"type": "object", "properties": {"post": _S["post"], "content": _S["content"], "author_name": _S["author_name"], "author_email": _S["author_email"], "parent": _S["parent"]}, "required": ["post", "content"]},
             outputSchema=_O["comment"]),
        Tool(name="wp_update_comment", description="Moderate a comment (approve/trash/spam)",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "status": _S["status"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        # ── WORDPRESS TAXONOMIES ─────────────────────────────────
        Tool(name="wp_list_categories", description="List all categories",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["list"]),
        Tool(name="wp_create_category", description="Create a new category",
             inputSchema={"type": "object", "properties": {"name": _S["name"], "slug": _S["slug"], "description": _S["description"]}, "required": ["name"]},
             outputSchema=_O["created"]),
        Tool(name="wp_update_category", description="Update a category name or description",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "name": _S["name"], "slug": _S["slug"], "description": _S["description"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_delete_category", description="Delete a category permanently",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_list_tags", description="List all tags",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["list"]),
        Tool(name="wp_create_tag", description="Create a new tag",
             inputSchema={"type": "object", "properties": {"name": _S["name"], "slug": _S["slug"], "description": _S["description"]}, "required": ["name"]},
             outputSchema=_O["created"]),
        # ── WORDPRESS MENUS ──────────────────────────────────────
        Tool(name="wp_list_menus", description="List navigation menus",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["list"]),
        Tool(name="wp_get_menu", description="Get a navigation menu by ID",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["menu"]),
        Tool(name="wp_create_menu", description="Create a new navigation menu",
             inputSchema={"type": "object", "properties": {"name": _S["name"]}, "required": ["name"]},
             outputSchema=_O["created"]),
        Tool(name="wp_get_menu_items", description="Get items for a menu",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema=_O["menu"]),
        Tool(name="wp_create_menu_item", description="Add item to a menu",
             inputSchema={"type": "object", "properties": {"title": _S["title"], "url": _S["url"], "menu_id": _S["menu_id"], "order": _S["order"]}, "required": ["title", "url", "menu_id"]},
             outputSchema=_O["created"]),
        Tool(name="wp_get_menu_locations", description="Get all menu locations and their assigned menus",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["menu_locations"]),
        # ── WORDPRESS SETTINGS ───────────────────────────────────
        Tool(name="wp_get_settings", description="Get site settings (title, description, timezone, etc.)",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["settings"]),
        Tool(name="wp_update_settings", description="Update site settings",
             inputSchema={"type": "object", "properties": {"title": _S["title"], "description": _S["title"], "timezone": _S["title"]}},
             outputSchema=_O["ok"]),
        Tool(name="wp_get_site_info", description="Get WordPress site info: version, routes, namespaces",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["site_info"]),
        # ── WORDPRESS BLOCKS ─────────────────────────────────────
        Tool(name="wp_list_blocks", description="List reusable blocks/patterns",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["list"]),
        Tool(name="wp_get_block", description="Get a reusable block by ID with content",
             inputSchema={"type": "object", "properties": {"id": _S["id"]}, "required": ["id"]},
             outputSchema={"type": "object", "properties": {"id": {"type": "integer"}, "title": {"type": "string"}, "content": {"type": "string"}}}),
        Tool(name="wp_create_block", description="Create a reusable block",
             inputSchema={"type": "object", "properties": {"title": _S["title"], "content": _S["content"]}, "required": ["title", "content"]},
             outputSchema=_O["created"]),
        Tool(name="wp_update_block", description="Update a reusable block content",
             inputSchema={"type": "object", "properties": {"id": _S["id"], "title": _S["title"], "content": _S["content"]}, "required": ["id"]},
             outputSchema=_O["ok"]),
        # ── WORDPRESS SEARCH / THEMES ────────────────────────────
        Tool(name="wp_search", description="Search posts, pages, and other content by query",
             inputSchema={"type": "object", "properties": {"query": _S["query"], "type": _S["type"], "subtype": _S["subtype"], "per_page": _S["per_page"]}, "required": ["query"]},
             outputSchema=_O["list"]),
        Tool(name="wp_list_themes", description="List themes (active + available)",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["themes"]),
        # ── ASTRA ────────────────────────────────────────────────
        Tool(name="wp_astra_get_settings", description="Get all Astra theme settings (header, footer, colors, typography)",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["astra_settings"]),
        Tool(name="wp_astra_update_settings", description="Update Astra theme settings. Use merge=true (default) to merge with existing, false to replace. Supports menu_locations and theme_mods.",
             inputSchema={"type": "object", "properties": {"settings": _S["settings"], "merge": _S["merge"], "menu_locations": _S["menu_locations"], "theme_mods": _S["theme_mods"]}, "required": ["settings"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_astra_set_menu_location", description="Assign a menu to an Astra header/footer location",
             inputSchema={"type": "object", "properties": {"menu_id": _S["id"], "location": _S["location"]}, "required": ["menu_id", "location"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_astra_get_setting", description="Get a single Astra setting by its key name (e.g. header-button1-text)",
             inputSchema={"type": "object", "properties": {"key": _S["key"]}, "required": ["key"]},
             outputSchema=_O["astra_setting"]),
        Tool(name="wp_astra_get_header_builder", description="Get the current header builder layout — slot assignments for desktop and mobile",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["astra_header"]),
        Tool(name="wp_astra_set_header_item", description='Set component(s) in a header slot. e.g. area=desktop, section=primary, slot=primary_right, items=["button-1"]',
             inputSchema={"type": "object", "properties": {"area": _S["area"], "section": _S["section"], "slot": _S["slot"], "items": _S["items"]}, "required": ["area", "section", "slot", "items"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_astra_configure_button", description="Batch-configure a header button: text, link, colors, radius, size.",
             inputSchema={"type": "object", "properties": {"button": _S["button"], "text": _S["text"], "url": _S["url"], "bg_color": _S["bg_color"], "text_color": _S["text_color"], "bg_hover_color": _S["bg_hover_color"], "radius": _S["radius"], "font_size": _S["font_size"]}, "required": ["button"]},
             outputSchema=_O["ok"]),
        Tool(name="wp_astra_configure_account", description="Configure the Astra account widget — shows login link when logged out, profile link when logged in.",
             inputSchema={"type": "object", "properties": {"logged_out_text": _S["logged_out_text"], "logged_in_text": _S["logged_in_text"], "login_url": _S["login_url"], "logout_url": _S["logout_url"], "login_style": _S["login_style"], "logout_style": _S["logout_style"]}},
             outputSchema=_O["ok"]),
        # ── WORDPRESS UTILITY ────────────────────────────────────
        Tool(name="wp_raw_request", description="Make any authenticated WP REST API request. endpoint=/wp/v2/pages or full URL",
             inputSchema={"type": "object", "properties": {"endpoint": _S["endpoint"], "method": _S["method"], "body": _S["body"]}, "required": ["endpoint"]},
             outputSchema=_O["raw_api"]),
        Tool(name="wp_get_rest_index", description="Get the WP REST API index (all available routes)",
             inputSchema={"type": "object", "properties": {}},
             outputSchema=_O["rest_index"]),

        # ── FILE READER ──────────────────────────────────────────
        Tool(name="file_reader_read_file", description="Read any file: PDF, DOCX, PPTX, XLSX, images, audio, text, CSV, HTML, Markdown. Auto-detect format.",
             inputSchema={"type": "object", "properties": {"path": _S["path"], "limit": _S["limit"]}, "required": ["path"]},
             outputSchema=_O["file_content"]),
        Tool(name="file_reader_read_image", description="Read an image file and return base64 data with MIME type",
             inputSchema={"type": "object", "properties": {"path": _S["path"]}, "required": ["path"]},
             outputSchema=_O["file_image"]),
        Tool(name="file_reader_convert_to_markdown", description="Convert any document (PDF, DOCX, PPTX, XLSX, HTML) to clean markdown text",
             inputSchema={"type": "object", "properties": {"path": _S["path"], "limit": _S["limit"]}, "required": ["path"]},
             outputSchema=_O["file_content"]),
        Tool(name="file_reader_list_directory", description="List files and subdirectories in a directory",
             inputSchema={"type": "object", "properties": {"path": _S["path"], "limit": _S["limit"]}, "required": ["path"]},
             outputSchema=_O["file_list"]),
        Tool(name="file_reader_get_file_info", description="Get metadata about a file (size, type, modified date)",
             inputSchema={"type": "object", "properties": {"path": _S["path"]}, "required": ["path"]},
             outputSchema=_O["file_info"]),
        Tool(name="file_reader_search_in_file", description="Search for a pattern in a file's content (supports PDF, DOCX, etc.)",
             inputSchema={"type": "object", "properties": {"path": _S["path"], "pattern": _S["pattern"], "limit": _S["limit"]}, "required": ["path", "pattern"]},
             outputSchema=_O["file_search"]),

        # ── cPanel DEPLOY ────────────────────────────────────────
        Tool(name="boss_deploy", description="Déploie le code BOSS sur cPanel (git pull + rsync). repo: bosscore, telet, ou all.",
             inputSchema={"type": "object", "properties": {"repo": _S["repo"]}, "required": ["repo"]},
             outputSchema=_O["deploy"]),

        # ── GIT VERSION CONTROL ──────────────────────────────────
        Tool(name="boss_git_push", description="Git add + commit + push. message: commit message obligatoire. Sur Windows retourne la commande bash à exécuter manuellement.",
             inputSchema={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
             outputSchema=_O["git_push"]),
    ]
