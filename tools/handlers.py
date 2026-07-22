"""Handlers BOSSCORE MCP PACK — WordPress + Fichiers + Déploiement cPanel."""

import json, os, sys, logging, base64, mimetypes, tempfile, subprocess
from typing import Any

import httpx
from mcp.types import TextContent

logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
log = logging.getLogger(__name__)

# ── CONFIG ──────────────────────────────────────────────────────────────────────

WP_URL  = os.environ.get("WORDPRESS_URL", "").rstrip("/")
WP_USER = os.environ.get("WORDPRESS_USERNAME", "")
WP_PASS = os.environ.get("WORDPRESS_APP_PASSWORD", "")
DEPLOY_TOKEN  = os.environ.get("DEPLOY_TOKEN", "")
DEPLOY_URL    = "https://core.bosserpnext.com/deploy.php"
BOSSCORE_WS   = os.environ.get("BOSSCORE_WORKSPACE", r"H:\Documents\Uncompressed\byContext\ResearchCenter\FetichesDesSciences\pratique\in-infrastructure-management")

# ── HELPERS ─────────────────────────────────────────────────────────────────────

def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2) if not isinstance(data, str) else data)]

def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error: {msg}")]

def _paged(endpoint: str, per_page: int = 50) -> str:
    sep = "&" if "?" in endpoint else "?"
    return f"{endpoint}{sep}per_page={per_page}"

def _env_check() -> str:
    """Vérifie que les variables d'environnement WP sont configurées. Retourne '' si OK."""
    if not WP_URL:  return "WORDPRESS_URL non défini"
    if not WP_USER: return "WORDPRESS_USERNAME non défini"
    if not WP_PASS: return "WORDPRESS_APP_PASSWORD non défini"
    return ""

# ── WORDPRESS CLIENT ────────────────────────────────────────────────────────────

WP_API_V2 = f"{WP_URL}/wp-json/wp/v2"
WP_API_V1 = f"{WP_URL}/wp-json/bosscore/v1"

async def _wp_req(method: str, path: str, **kw) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method, path, auth=(WP_USER, WP_PASS), **kw)
        r.raise_for_status()
        return r.json() if r.text else {}

# ── WORDPRESS HANDLERS ──────────────────────────────────────────────────────────

async def wp_list_pages(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/pages"))
    return _ok([{"id": p["id"], "title": p["title"]["rendered"], "slug": p["slug"], "status": p["status"]} for p in data])

async def wp_get_page(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/pages/{args['id']}")
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "content": data["content"]["rendered"], "slug": data["slug"], "status": data["status"], "meta": data.get("meta", {})})

async def wp_create_page(args: dict) -> list[TextContent]:
    body = {"title": args["title"], "content": args.get("content", ""), "status": args.get("status", "publish")}
    data = await _wp_req("POST", f"{WP_API_V2}/pages", json=body)
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "slug": data["slug"], "link": data["link"]})

async def wp_update_page(args: dict) -> list[TextContent]:
    body = {k: args[k] for k in ("title", "content", "status") if k in args}
    if "meta" in args: body["meta"] = args["meta"]
    data = await _wp_req("PUT", f"{WP_API_V2}/pages/{args['id']}", json=body)
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "status": data["status"], "modified": data["modified"]})

async def wp_delete_page(args: dict) -> list[TextContent]:
    await _wp_req("DELETE", f"{WP_API_V2}/pages/{args['id']}", params={"force": True})
    return _ok({"deleted": True, "id": args["id"]})

async def wp_list_posts(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/posts"))
    return _ok([{"id": p["id"], "title": p["title"]["rendered"], "slug": p["slug"], "status": p["status"]} for p in data])

async def wp_get_post(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/posts/{args['id']}")
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "content": data["content"]["rendered"], "slug": data["slug"], "status": data["status"]})

async def wp_create_post(args: dict) -> list[TextContent]:
    body = {"title": args["title"], "content": args.get("content", ""), "status": args.get("status", "publish")}
    data = await _wp_req("POST", f"{WP_API_V2}/posts", json=body)
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "slug": data["slug"]})

async def wp_update_post(args: dict) -> list[TextContent]:
    body = {k: args[k] for k in ("title", "content", "status") if k in args}
    data = await _wp_req("PUT", f"{WP_API_V2}/posts/{args['id']}", json=body)
    return _ok({"id": data["id"], "status": data["status"], "modified": data["modified"]})

async def wp_delete_post(args: dict) -> list[TextContent]:
    await _wp_req("DELETE", f"{WP_API_V2}/posts/{args['id']}", params={"force": True})
    return _ok({"deleted": True, "id": args["id"]})

async def wp_list_media(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/media"))
    return _ok([{"id": m["id"], "title": m["title"]["rendered"], "mime": m["mime_type"], "url": m.get("source_url", "")} for m in data])

async def wp_get_media(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/media/{args['id']}")
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "url": data.get("source_url", ""), "alt": data.get("alt_text", ""), "mime": data["mime_type"], "sizes": data.get("media_details", {}).get("sizes", {})})

async def wp_upload_media(args: dict) -> list[TextContent]:
    async with httpx.AsyncClient() as c:
        r = await c.get(args["source_url"]); r.raise_for_status()
        ct = r.headers.get("content-type", "image/png")
        files = {"file": (args.get("title", "upload"), r.content, ct)}
        data = await _wp_req("POST", f"{WP_API_V2}/media", files=files)
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "url": data.get("source_url", "")})

async def wp_update_media(args: dict) -> list[TextContent]:
    body = {k: args[k] for k in ("title", "alt_text", "caption", "description") if k in args}
    data = await _wp_req("PUT", f"{WP_API_V2}/media/{args['id']}", json=body)
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "alt": data.get("alt_text", "")})

async def wp_delete_media(args: dict) -> list[TextContent]:
    await _wp_req("DELETE", f"{WP_API_V2}/media/{args['id']}", params={"force": True})
    return _ok({"deleted": True, "id": args["id"]})

async def wp_list_users(args: dict) -> list[TextContent]:
    try:
        data = await _wp_req("GET", _paged(f"{WP_API_V2}/users"))
        return _ok([{"id": u["id"], "name": u["name"], "slug": u["slug"]} for u in data])
    except Exception as e:
        if "403" in str(e): return _err("Forbidden: Application Password may lack 'list_users' capability. Use wp_raw_request instead.")
        raise

async def wp_get_user(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/users/{args['id']}")
    return _ok({"id": data["id"], "name": data["name"], "slug": data["slug"], "avatar": data.get("avatar_urls", {})})

async def wp_create_user(args: dict) -> list[TextContent]:
    body = {"username": args["username"], "password": args["password"], "email": args.get("email", "")}
    data = await _wp_req("POST", f"{WP_API_V2}/users", json=body)
    return _ok({"id": data["id"], "username": data["slug"], "name": data["name"]})

async def wp_get_user_me(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/users/me")
    return _ok({"id": data["id"], "name": data["name"], "slug": data["slug"], "avatar": data.get("avatar_urls", {})})

async def wp_update_user(args: dict) -> list[TextContent]:
    body = {k: args[k] for k in ("name", "email", "password", "roles") if k in args}
    data = await _wp_req("PUT", f"{WP_API_V2}/users/{args['id']}", json=body)
    return _ok({"id": data["id"], "name": data["name"]})

async def wp_delete_user(args: dict) -> list[TextContent]:
    await _wp_req("DELETE", f"{WP_API_V2}/users/{args['id']}", params={"force": True, "reassign": args.get("reassign", 1)})
    return _ok({"deleted": True, "id": args["id"]})

async def wp_list_comments(args: dict) -> list[TextContent]:
    params = {"per_page": 10, "orderby": "date", "order": "desc"}
    if "post" in args: params["post"] = args["post"]
    data = await _wp_req("GET", f"{WP_API_V2}/comments", params=params)
    return _ok([{"id": c["id"], "post": c.get("post", 0), "author": c.get("author_name", ""), "content": c["content"]["rendered"][:200], "status": c["status"]} for c in data])

async def wp_create_comment(args: dict) -> list[TextContent]:
    body = {"post": args["post"], "content": args["content"]}
    if "parent" in args: body["parent"] = args["parent"]
    if "author_name" in args: body["author_name"] = args["author_name"]
    if "author_email" in args: body["author_email"] = args["author_email"]
    data = await _wp_req("POST", f"{WP_API_V2}/comments", json=body)
    return _ok({"id": data["id"], "post": data.get("post", 0), "status": data["status"]})

async def wp_update_comment(args: dict) -> list[TextContent]:
    body = {k: args[k] for k in ("content", "status") if k in args}
    data = await _wp_req("PUT", f"{WP_API_V2}/comments/{args['id']}", json=body)
    return _ok({"id": data["id"], "status": data["status"]})

async def wp_list_categories(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/categories"))
    return _ok([{"id": c["id"], "name": c["name"], "slug": c["slug"], "count": c["count"]} for c in data])

async def wp_list_tags(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/tags"))
    return _ok([{"id": t["id"], "name": t["name"], "slug": t["slug"], "count": t["count"]} for t in data])

async def wp_create_category(args: dict) -> list[TextContent]:
    body = {"name": args["name"], "slug": args.get("slug", ""), "description": args.get("description", "")}
    data = await _wp_req("POST", f"{WP_API_V2}/categories", json=body)
    return _ok({"id": data["id"], "name": data["name"], "slug": data["slug"]})

async def wp_update_category(args: dict) -> list[TextContent]:
    body = {k: args[k] for k in ("name", "slug", "description") if k in args}
    data = await _wp_req("PUT", f"{WP_API_V2}/categories/{args['id']}", json=body)
    return _ok({"id": data["id"], "name": data["name"]})

async def wp_delete_category(args: dict) -> list[TextContent]:
    await _wp_req("DELETE", f"{WP_API_V2}/categories/{args['id']}", params={"force": True})
    return _ok({"deleted": True, "id": args["id"]})

async def wp_create_tag(args: dict) -> list[TextContent]:
    body = {"name": args["name"], "slug": args.get("slug", ""), "description": args.get("description", "")}
    data = await _wp_req("POST", f"{WP_API_V2}/tags", json=body)
    return _ok({"id": data["id"], "name": data["name"], "slug": data["slug"]})

async def wp_list_menus(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/menus"))
    return _ok([{"id": m["id"], "name": m["name"], "slug": m["slug"]} for m in data])

async def wp_get_menu(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/menus/{args['id']}")
    return _ok({"id": data["id"], "name": data["name"], "slug": data["slug"], "locations": data.get("locations", [])})

async def wp_create_menu(args: dict) -> list[TextContent]:
    body = {"name": args["name"]}
    data = await _wp_req("POST", f"{WP_API_V2}/menus", json=body)
    return _ok({"id": data["id"], "name": data["name"], "slug": data["slug"]})

async def wp_get_menu_items(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/menu-items"), params={"menus": args["id"]})
    return _ok([{"id": i["id"], "title": i["title"]["rendered"], "url": i.get("url", ""), "order": i.get("menu_order", 0)} for i in data])

async def wp_create_menu_item(args: dict) -> list[TextContent]:
    body = {"title": args["title"], "url": args["url"], "menus": args["menu_id"]}
    if "order" in args: body["menu_order"] = args["order"]
    data = await _wp_req("POST", f"{WP_API_V2}/menu-items", json=body)
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "url": data.get("url", "")})

async def wp_get_menu_locations(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/menu-locations")
    return _ok({k: {"name": v["name"], "menu": v.get("menu", 0)} for k, v in data.items()})

async def wp_get_settings(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/settings")
    return _ok(data)

async def wp_update_settings(args: dict) -> list[TextContent]:
    data = await _wp_req("PUT", f"{WP_API_V2}/settings", json=args)
    return _ok(data)

async def wp_get_site_info(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_URL}/wp-json")
    return _ok({"name": data.get("name", ""), "description": data.get("description", ""), "url": data.get("url", ""), "namespaces": data.get("namespaces", []), "routes_count": len(data.get("routes", {}))})

async def wp_list_blocks(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", _paged(f"{WP_API_V2}/blocks"))
    return _ok([{"id": b["id"], "title": b["title"]["rendered"], "slug": b["slug"]} for b in data])

async def wp_get_block(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/blocks/{args['id']}")
    return _ok({"id": data["id"], "title": data["title"]["rendered"], "content": data["content"]["rendered"][:3000]})

async def wp_create_block(args: dict) -> list[TextContent]:
    body = {"title": args["title"], "content": args["content"], "status": "publish"}
    data = await _wp_req("POST", f"{WP_API_V2}/blocks", json=body)
    return _ok({"id": data["id"], "title": data["title"]["rendered"]})

async def wp_update_block(args: dict) -> list[TextContent]:
    body = {k: args[k] for k in ("title", "content", "status") if k in args}
    data = await _wp_req("PUT", f"{WP_API_V2}/blocks/{args['id']}", json=body)
    return _ok({"id": data["id"], "title": data["title"]["rendered"]})

async def wp_search(args: dict) -> list[TextContent]:
    params = {"search": args["query"], "per_page": args.get("per_page", 10)}
    if "type" in args: params["type"] = args["type"]
    if "subtype" in args: params["subtype"] = args["subtype"]
    data = await _wp_req("GET", f"{WP_API_V2}/search", params=params)
    return _ok([{"id": r["id"], "title": r["title"], "type": r.get("subtype", r.get("type", "")), "url": r.get("url", "")} for r in data])

async def wp_list_themes(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_API_V2}/themes?status=active")
    active = data[0] if data else {}
    all_themes = await _wp_req("GET", f"{WP_API_V2}/themes")
    return _ok({"active": {"name": active.get("name", {}).get("rendered", ""), "version": active.get("version", ""), "stylesheet": active.get("stylesheet", "")} if active else {}, "available": [{"name": t.get("name", {}).get("rendered", ""), "stylesheet": t["stylesheet"]} for t in all_themes]})

# ── ASTRA HANDLERS ──────────────────────────────────────────────────────────────

async def wp_astra_get_settings(args: dict) -> list[TextContent]:
    try:
        data = await _wp_req("GET", f"{WP_API_V1}/astra-settings")
        return _ok(data.get("settings", data))
    except Exception as e:
        return _err(f"Astra endpoint unavailable: {e}")

async def wp_astra_update_settings(args: dict) -> list[TextContent]:
    body = {"settings": args.get("settings", {}), "merge": args.get("merge", True)}
    if "menu_locations" in args: body["menu_locations"] = args["menu_locations"]
    if "theme_mods" in args: body["theme_mods"] = args["theme_mods"]
    try:
        data = await _wp_req("POST", f"{WP_API_V1}/astra-settings", json=body)
        return _ok({"success": data.get("success", False), "merged": data.get("merged", True), "keys_updated": len(args.get("settings", {}))})
    except Exception as e:
        return _err(f"Astra endpoint unavailable: {e}")

async def wp_astra_set_menu_location(args: dict) -> list[TextContent]:
    return await wp_astra_update_settings({"settings": {}, "merge": True, "menu_locations": {args["location"]: args["menu_id"]}})

async def wp_astra_get_setting(args: dict) -> list[TextContent]:
    try:
        data = await _wp_req("GET", f"{WP_API_V1}/astra-settings")
        settings = data.get("settings", data)
        value = settings.get(args["key"], "--ABSENT--")
        return _ok({"key": args["key"], "value": value})
    except Exception as e:
        return _err(f"Astra endpoint unavailable: {e}")

async def wp_astra_get_header_builder(args: dict) -> list[TextContent]:
    try:
        data = await _wp_req("GET", f"{WP_API_V1}/astra-settings")
        settings = data.get("settings", data)
        desktop = settings.get("header-desktop-items", {})
        mobile = settings.get("header-mobile-items", {})

        def _slots(section, kind):
            return {k: v for k, v in section.items() if kind in k}

        result = {
            "desktop": {"primary": _slots(desktop.get("primary", {}), "primary"),
                        "above": _slots(desktop.get("above", {}), "above"),
                        "below": _slots(desktop.get("below", {}), "below")},
            "mobile":  {"primary": _slots(mobile.get("primary", {}), "primary"),
                        "above": _slots(mobile.get("above", {}), "above"),
                        "below": _slots(mobile.get("below", {}), "below"),
                        "popup": mobile.get("popup", {})}
        }
        return _ok(result)
    except Exception as e:
        return _err(f"Astra endpoint unavailable: {e}")

async def wp_astra_set_header_item(args: dict) -> list[TextContent]:
    try:
        data = await _wp_req("GET", f"{WP_API_V1}/astra-settings")
        settings = data.get("settings", data)
        key = "header-desktop-items" if args["area"] == "desktop" else "header-mobile-items"
        header = settings.get(key, {})
        section = header.setdefault(args["section"], {})
        section[args["slot"]] = args["items"]
        header["flag"] = True
        body = {"settings": {key: header}, "merge": True}
        data2 = await _wp_req("POST", f"{WP_API_V1}/astra-settings", json=body)
        return _ok({"success": data2.get("success", False), "slot": f"{args['section']}/{args['slot']}", "items": args["items"]})
    except Exception as e:
        return _err(f"Failed: {e}")

async def wp_astra_configure_button(args: dict) -> list[TextContent]:
    btn = args["button"]
    settings = {}
    if "text" in args: settings[f"header-{btn}-text"] = args["text"]
    if "url" in args: settings[f"header-{btn}-link-option"] = {"url": args["url"], "new_tab": args.get("new_tab", ""), "link_rel": args.get("link_rel", "")}
    if "bg_color" in args: settings[f"header-{btn}-back-color"] = {"desktop": args["bg_color"], "tablet": args["bg_color"], "mobile": args["bg_color"]}
    if "text_color" in args: settings[f"header-{btn}-text-color"] = {"desktop": args["text_color"], "tablet": args["text_color"], "mobile": args["text_color"]}
    if "bg_hover_color" in args: settings[f"header-{btn}-back-h-color"] = {"desktop": args["bg_hover_color"], "tablet": args["bg_hover_color"], "mobile": args["bg_hover_color"]}
    if "radius" in args: settings[f"header-{btn}-border-radius"] = args["radius"]
    if "font_size" in args: settings[f"header-{btn}-font-size"] = {"desktop": args["font_size"], "tablet": "", "mobile": "", "desktop-unit": "px", "tablet-unit": "px", "mobile-unit": "px"}
    if not settings: return _err("No settings provided")
    return await wp_astra_update_settings({"settings": settings, "merge": True})

async def wp_astra_configure_account(args: dict) -> list[TextContent]:
    settings = {}
    if "logged_out_text" in args: settings["header-account-logged-out-text"] = args["logged_out_text"]
    if "logged_in_text" in args: settings["header-account-logged-in-text"] = args["logged_in_text"]
    if "login_url" in args: settings["header-account-login-link"] = {"url": args["login_url"], "new_tab": False, "link_rel": ""}
    if "logout_url" in args: settings["header-account-logout-link"] = {"url": args["logout_url"], "new_tab": False, "link_rel": ""}
    if "login_style" in args: settings["header-account-login-style"] = args["login_style"]
    if "logout_style" in args: settings["header-account-logout-style"] = args["logout_style"]
    if not settings: return _err("No settings provided")
    return await wp_astra_update_settings({"settings": settings, "merge": True})

async def wp_raw_request(args: dict) -> list[TextContent]:
    endpoint = args["endpoint"]
    method = args.get("method", "GET")
    body = args.get("body")
    url = endpoint if endpoint.startswith("http") else f"{WP_URL}/wp-json{endpoint}"
    async with httpx.AsyncClient(timeout=30) as c:
        kw = {}
        if body: kw["json"] = json.loads(body) if isinstance(body, str) else body
        r = await c.request(method, url, auth=(WP_USER, WP_PASS), **kw)
        result = {"status": r.status_code, "body": r.text[:5000]} if r.text else {"status": r.status_code}
        return _ok(result)

async def wp_get_rest_index(args: dict) -> list[TextContent]:
    data = await _wp_req("GET", f"{WP_URL}/wp-json")
    routes = {k: {"methods": v.get("methods", []), "endpoint": k} for k, v in sorted(data.get("routes", {}).items()) if not k.startswith("/oembed")}
    return _ok({"routes_count": len(routes), "namespaces": data.get("namespaces", []), "routes_sample": dict(list(routes.items())[:30])})

# ── FILE READER ─────────────────────────────────────────────────────────────────

# Imports paresseux (ne sont chargés que si un outil fichier est appelé)
_PDF_READER = None
_MARKDOWN = None
_OCR_AVAIL = False
_WHISPER_AVAIL = False
_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

def _lazy_imports():
    global _PDF_READER, _MARKDOWN, _OCR_AVAIL
    if _PDF_READER is None:
        from PyPDF2 import PdfReader; _PDF_READER = PdfReader
        from markitdown import MarkItDown; _MARKDOWN = MarkItDown()
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            _OCR_AVAIL = os.path.exists(pytesseract.pytesseract.tesseract_cmd)
        except Exception:
            pass

def _guess_type(path: str) -> str:
    from os.path import splitext
    ext = splitext(path)[1].lower()
    types = {
        '.pdf': 'pdf', '.docx': 'docx', '.doc': 'docx', '.pptx': 'pptx', '.ppt': 'pptx',
        '.xlsx': 'xlsx', '.xls': 'xlsx',
        '.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.gif': 'image',
        '.bmp': 'image', '.webp': 'image', '.tiff': 'image', '.tif': 'image', '.svg': 'image',
        '.md': 'markdown', '.txt': 'text', '.csv': 'csv', '.json': 'json',
        '.html': 'html', '.htm': 'html', '.xml': 'html',
        '.mp3': 'audio', '.wav': 'audio', '.ogg': 'audio', '.flac': 'audio',
        '.aac': 'audio', '.m4a': 'audio', '.opus': 'audio', '.wma': 'audio',
        '.mp4': 'video', '.mkv': 'video', '.avi': 'video', '.mov': 'video',
        '.webm': 'video', '.flv': 'video',
        '.py': 'text', '.js': 'text', '.css': 'text', '.tsx': 'code', '.jsx': 'code',
        '.php': 'text', '.sh': 'text', '.yaml': 'text', '.yml': 'text',
    }
    return types.get(ext, 'unknown')

async def _ollama_vision(path: str) -> str:
    try:
        with open(path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode()
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"{_OLLAMA_URL}/api/generate", json={
                "model": "minicpm-v:latest",
                "prompt": "Décris cette image en français, de façon précise et concise.",
                "images": [img_b64], "stream": False,
            })
        return r.json().get("response", "").strip()
    except Exception:
        return ""

def _transcribe_audio(path: str) -> str:
    global _WHISPER_AVAIL
    if not _WHISPER_AVAIL:
        try:
            from faster_whisper import WhisperModel
            global _WHISPER_MODEL
            _WHISPER_MODEL = WhisperModel("tiny", device="cpu", compute_type="int8")
            _WHISPER_AVAIL = True
        except Exception:
            return ""
    try:
        segments, info = _WHISPER_MODEL.transcribe(path, language="fr", beam_size=5)
        return " ".join(seg.text for seg in segments).strip()
    except Exception:
        return ""

async def file_reader_read_file(args: dict) -> list[TextContent]:
    _lazy_imports()
    path = args["path"]
    if not os.path.exists(path): return _err(f"File not found: {path}")
    ftype = _guess_type(path)
    limit = args.get("limit", 5000)
    size = os.path.getsize(path)

    try:
        if ftype == 'pdf':
            reader = _PDF_READER(path)
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n\n".join(pages).strip()
            if len(text) > 100:
                return _ok(f"[PDF · {len(reader.pages)} pages]\n{text[:limit]}")
            try:
                md = _MARKDOWN.convert(path)
                if md.text_content.strip():
                    return _ok(f"[PDF · {len(reader.pages)} pages · converted]\n{md.text_content[:limit]}")
            except Exception: pass
            if _OCR_AVAIL:
                import pytesseract; from PIL import Image
                ocr_pages = []
                for i, page in enumerate(reader.pages):
                    if i >= 10: ocr_pages.append(f"... (page {i+1}/{len(reader.pages)} skipped)"); break
                    for image_obj in page.images:
                        try:
                            img = Image.open(image_obj.data)
                            page_text = pytesseract.image_to_string(img, lang='fra+eng')
                            if page_text.strip(): ocr_pages.append(f"--- Page {i+1} ---\n{page_text.strip()}")
                        except Exception: pass
                if ocr_pages: return _ok(f"[PDF · {len(reader.pages)} pages · OCR]\n" + "\n\n".join(ocr_pages)[:limit])
            return _ok(f"[PDF · {len(reader.pages)} pages · no extractable text]")

        elif ftype == 'image':
            from PIL import Image
            img = Image.open(path)
            mime = mimetypes.guess_type(path)[0] or "image/png"
            info = f"[Image: {img.size[0]}x{img.size[1]} | {img.format} | {size} bytes]"
            vision_desc = await _ollama_vision(path)
            result = info
            if vision_desc: result += f"\n\n--- Description ---\n{vision_desc}"
            if _OCR_AVAIL:
                try:
                    import pytesseract
                    ocr_text = pytesseract.image_to_string(img, lang='fra+eng').strip()
                    if ocr_text: result += f"\n\n--- OCR ---\n{ocr_text[:limit]}"
                except Exception: pass
            return _ok(result)

        elif ftype in ('docx', 'pptx', 'xlsx', 'html', 'csv', 'markdown'):
            result = _MARKDOWN.convert(path)
            return _ok(result.text_content[:limit])

        elif ftype == 'audio':
            result = f"[Audio: {os.path.basename(path)} | {size} bytes | {size/1024:.1f} KB]"
            transcription = _transcribe_audio(path)
            if transcription: result += f"\n\n--- Transcription ---\n{transcription[:limit]}"
            return _ok(result)

        elif ftype == 'video':
            result = f"[Video: {os.path.basename(path)} | {size} bytes | {size/1024/1024:.1f} MB]"
            try:
                import moviepy.editor as mp
                audio_path = os.path.join(tempfile.gettempdir(), f"_file_reader_audio_{os.getpid()}.wav")
                clip = mp.VideoFileClip(path)
                if clip.audio is not None:
                    clip.audio.write_audiofile(audio_path, logger=None); clip.close()
                    transcription = _transcribe_audio(audio_path)
                    os.unlink(audio_path)
                    if transcription: result += f"\n\n--- Transcription ---\n{transcription[:limit]}"
            except Exception: pass
            return _ok(result)

        else:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(limit) if limit else f.read()
                return _ok(content)
            except UnicodeDecodeError:
                with open(path, 'rb') as f: data = f.read(512)
                return _ok(f"[Binary: {os.path.basename(path)} | {size} bytes · cannot decode]\nHex: {data[:256].hex()}")
    except Exception as e:
        return _err(f"Cannot read {ftype}: {e}")

async def file_reader_read_image(args: dict) -> list[TextContent]:
    path = args["path"]
    if not os.path.exists(path): return _err(f"File not found: {path}")
    try:
        with open(path, 'rb') as f: data = base64.b64encode(f.read()).decode('utf-8')
        mime = mimetypes.guess_type(path)[0] or "image/png"
        return _ok(f"data:{mime};base64,{data[:500]}" if len(data) > 500 else f"data:{mime};base64,{data}")
    except Exception as e:
        return _err(f"Cannot read image: {e}")

async def file_reader_convert_to_markdown(args: dict) -> list[TextContent]:
    _lazy_imports()
    path = args["path"]
    if not os.path.exists(path): return _err(f"File not found: {path}")
    try:
        result = _MARKDOWN.convert(path)
        return _ok(result.text_content[:args.get("limit", 10000)])
    except Exception as e:
        return _err(f"Conversion failed: {e}")

async def file_reader_list_directory(args: dict) -> list[TextContent]:
    path = args["path"]
    if not os.path.isdir(path): return _err(f"Not a directory: {path}")
    try:
        entries = []
        for entry in sorted(os.listdir(path)):
            full = os.path.join(path, entry)
            entries.append({"name": entry, "type": "directory" if os.path.isdir(full) else "file", "size": os.path.getsize(full) if os.path.isfile(full) else 0})
        return _ok({"path": path, "count": len(entries), "entries": entries[:args.get("limit", 100)]})
    except Exception as e:
        return _err(str(e))

async def file_reader_get_file_info(args: dict) -> list[TextContent]:
    path = args["path"]
    if not os.path.exists(path): return _err(f"File not found: {path}")
    stat = os.stat(path)
    return _ok({"name": os.path.basename(path), "path": path, "size": stat.st_size, "type": _guess_type(path), "extension": os.path.splitext(path)[1], "modified": stat.st_mtime, "is_dir": os.path.isdir(path)})

async def file_reader_search_in_file(args: dict) -> list[TextContent]:
    _lazy_imports()
    path = args["path"]; pattern = args["pattern"]
    if not os.path.exists(path): return _err(f"File not found: {path}")
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        matches = [(i+1, line.rstrip()) for i, line in enumerate(lines) if pattern.lower() in line.lower()]
        return _ok({"path": path, "matches": len(matches), "results": matches[:args.get("limit", 20)]})
    except Exception:
        try:
            result = _MARKDOWN.convert(path)
            text = result.text_content
            if pattern.lower() in text.lower():
                idx = text.lower().find(pattern.lower())
                return _ok({"path": path, "matches": 1, "context": text[max(0, idx-100):idx+len(pattern)+100]})
            return _ok({"path": path, "matches": 0, "results": []})
        except Exception as e:
            return _err(f"Cannot search: {e}")

# ── cPanel DEPLOY ───────────────────────────────────────────────────────────────

async def boss_deploy(args: dict) -> list[TextContent]:
    repo = args.get("repo", "")
    if repo not in ("bosscore", "telet", "all"):
        return _err("Paramètre 'repo' requis : bosscore, telet, ou all.")
    if not DEPLOY_TOKEN:
        return _err("DEPLOY_TOKEN non défini dans les variables d'environnement.")

    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.get(DEPLOY_URL, params={"repo": repo, "token": DEPLOY_TOKEN})
            return _ok(r.text.strip())
    except httpx.HTTPError as e:
        return _err(f"Déploiement échoué: {e}")

# ── GIT VERSION CONTROL ──────────────────────────────────────────────────────────

async def boss_git_push(args: dict) -> list[TextContent]:
    """Git add + commit + push dans le workspace companies.
    Args: message (commit message), path (optionnel, relatif au workspace).
    """
    message = args.get("message", "")
    if not message:
        return _err("Paramètre 'message' requis.")

    rel_path = args.get("path", "").lstrip("/").lstrip("\\")
    ws = BOSSCORE_WS
    if not os.path.isdir(ws):
        return _err(f"BOSSCORE_WORKSPACE introuvable : {ws}")

    output = []
    try:
        # git add
        cmd = ["git", "add"]
        cmd.append(rel_path if rel_path else "-A")
        r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=30)
        output.append(f"$ git add {'-A' if not rel_path else rel_path}")
        if r.returncode != 0:
            return _err(f"git add échoué: {r.stderr.strip()}")

        # git status (pour info)
        r = subprocess.run(["git", "status", "--short"], cwd=ws, capture_output=True, text=True, timeout=10)
        if r.stdout.strip():
            output.append(f"Staged:\n{r.stdout.strip()}")
        else:
            output.append("(nothing to commit)")

        # git commit
        r = subprocess.run(["git", "commit", "-m", message], cwd=ws, capture_output=True, text=True, timeout=30)
        output.append(f"\n$ git commit -m \"{message}\"")
        output.append(r.stderr.strip() if r.stderr else r.stdout.strip())
        if r.returncode != 0 and "nothing to commit" not in r.stdout:
            return _err(f"git commit échoué: {r.stderr.strip()}")

        # git push
        r = subprocess.run(["git", "push", "origin", "master"], cwd=ws, capture_output=True, text=True, timeout=60)
        output.append(f"\n$ git push origin master")
        output.append(r.stderr.strip() if r.stderr else r.stdout.strip())
        if r.returncode != 0:
            return _err(f"git push échoué: {r.stderr.strip()}")

        output.append("\n✅ Push OK.")
        return _ok("\n".join(output))
    except subprocess.TimeoutExpired:
        return _err("Git operation timed out.")
    except Exception as e:
        return _err(f"Git error: {e}")

# ── DISPATCH ────────────────────────────────────────────────────────────────────

_HANDLERS = {
    "wp_list_pages": wp_list_pages, "wp_get_page": wp_get_page, "wp_create_page": wp_create_page,
    "wp_update_page": wp_update_page, "wp_delete_page": wp_delete_page,
    "wp_list_posts": wp_list_posts, "wp_get_post": wp_get_post, "wp_create_post": wp_create_post,
    "wp_update_post": wp_update_post, "wp_delete_post": wp_delete_post,
    "wp_list_media": wp_list_media, "wp_get_media": wp_get_media, "wp_upload_media": wp_upload_media,
    "wp_update_media": wp_update_media, "wp_delete_media": wp_delete_media,
    "wp_list_users": wp_list_users, "wp_get_user": wp_get_user, "wp_get_user_me": wp_get_user_me,
    "wp_create_user": wp_create_user, "wp_update_user": wp_update_user, "wp_delete_user": wp_delete_user,
    "wp_list_comments": wp_list_comments, "wp_create_comment": wp_create_comment, "wp_update_comment": wp_update_comment,
    "wp_list_categories": wp_list_categories, "wp_create_category": wp_create_category,
    "wp_update_category": wp_update_category, "wp_delete_category": wp_delete_category,
    "wp_list_tags": wp_list_tags, "wp_create_tag": wp_create_tag,
    "wp_list_menus": wp_list_menus, "wp_get_menu": wp_get_menu, "wp_create_menu": wp_create_menu,
    "wp_get_menu_items": wp_get_menu_items, "wp_create_menu_item": wp_create_menu_item,
    "wp_get_menu_locations": wp_get_menu_locations,
    "wp_get_settings": wp_get_settings, "wp_update_settings": wp_update_settings,
    "wp_get_site_info": wp_get_site_info,
    "wp_list_blocks": wp_list_blocks, "wp_get_block": wp_get_block,
    "wp_create_block": wp_create_block, "wp_update_block": wp_update_block,
    "wp_search": wp_search, "wp_list_themes": wp_list_themes,
    "wp_astra_get_settings": wp_astra_get_settings, "wp_astra_update_settings": wp_astra_update_settings,
    "wp_astra_set_menu_location": wp_astra_set_menu_location, "wp_astra_get_setting": wp_astra_get_setting,
    "wp_astra_get_header_builder": wp_astra_get_header_builder, "wp_astra_set_header_item": wp_astra_set_header_item,
    "wp_astra_configure_button": wp_astra_configure_button, "wp_astra_configure_account": wp_astra_configure_account,
    "wp_raw_request": wp_raw_request, "wp_get_rest_index": wp_get_rest_index,
    "file_reader_read_file": file_reader_read_file, "file_reader_read_image": file_reader_read_image,
    "file_reader_convert_to_markdown": file_reader_convert_to_markdown,
    "file_reader_list_directory": file_reader_list_directory, "file_reader_get_file_info": file_reader_get_file_info,
    "file_reader_search_in_file": file_reader_search_in_file,
    "boss_deploy": boss_deploy,
    "boss_git_push": boss_git_push,
}

async def dispatch(name: str, arguments: dict) -> list[TextContent]:
    err = _env_check()
    if err and name.startswith("wp_"):
        return _err(f"WordPress MCP non configuré : {err}")

    handler = _HANDLERS.get(name)
    if not handler:
        return _err(f"Unknown tool: {name}")
    try:
        return await handler(arguments if arguments else {})
    except Exception as e:
        return _err(f"{type(e).__name__}: {e}")
