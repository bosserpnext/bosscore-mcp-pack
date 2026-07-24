"""WordPress tools backed by a reusable REST client."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from ..core.errors import PolicyViolation, ValidationError
from ..core.registry import ToolSpec, object_schema
from .client import WordPressClient

JSON = dict[str, Any]
Handler = Callable[[JSON], Awaitable[Any]]

STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
OBJ = {"type": "object"}
STRINGS = {"type": "array", "items": {"type": "string"}}


def _rendered(value: Any) -> str:
    return value.get("rendered", "") if isinstance(value, dict) else str(value or "")


class WordPressProvider:
    def __init__(self, client: WordPressClient) -> None:
        self.client = client
        self.v2 = "/wp-json/wp/v2"
        self.boss = "/wp-json/bosscore/v1"

    async def _request(self, method: str, path: str, **kwargs):
        return await self.client.request(method, path, **kwargs)

    @staticmethod
    def _page_params(args: JSON, default: int = 50) -> JSON:
        return {
            "per_page": max(1, min(int(args.get("per_page", default)), 100)),
            "page": max(1, int(args.get("page", 1))),
        }

    async def list_pages(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/pages", params=self._page_params(args))
        return [{"id": p["id"], "title": _rendered(p["title"]), "slug": p["slug"], "status": p["status"]} for p in data]

    async def get_page(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/pages/{args['id']}", params={"context": args.get("context", "edit")})
        return {"id": data["id"], "title": _rendered(data["title"]), "content": data.get("content", {}).get("raw", _rendered(data.get("content"))), "slug": data["slug"], "status": data["status"], "meta": data.get("meta", {})}

    async def create_page(self, args: JSON):
        body = {"title": args["title"], "content": args.get("content", ""), "status": args.get("status", "publish")}
        data = await self._request("POST", f"{self.v2}/pages", json=body)
        return {"id": data["id"], "title": _rendered(data["title"]), "slug": data["slug"], "link": data["link"]}

    async def update_page(self, args: JSON):
        body = {key: args[key] for key in ("title", "content", "status", "meta") if key in args}
        data = await self._request("PUT", f"{self.v2}/pages/{args['id']}", json=body)
        return {"id": data["id"], "title": _rendered(data["title"]), "status": data["status"], "modified": data["modified"]}

    async def delete_page(self, args: JSON):
        force = bool(args.get("force", False))
        await self._request("DELETE", f"{self.v2}/pages/{args['id']}", params={"force": force})
        return {"action": "deleted" if force else "trashed", "id": args["id"]}

    async def list_posts(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/posts", params=self._page_params(args))
        return [{"id": p["id"], "title": _rendered(p["title"]), "slug": p["slug"], "status": p["status"]} for p in data]

    async def get_post(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/posts/{args['id']}", params={"context": args.get("context", "edit")})
        return {"id": data["id"], "title": _rendered(data["title"]), "content": data.get("content", {}).get("raw", _rendered(data.get("content"))), "slug": data["slug"], "status": data["status"]}

    async def create_post(self, args: JSON):
        data = await self._request("POST", f"{self.v2}/posts", json={"title": args["title"], "content": args.get("content", ""), "status": args.get("status", "publish")})
        return {"id": data["id"], "title": _rendered(data["title"]), "slug": data["slug"]}

    async def update_post(self, args: JSON):
        body = {key: args[key] for key in ("title", "content", "status") if key in args}
        data = await self._request("PUT", f"{self.v2}/posts/{args['id']}", json=body)
        return {"id": data["id"], "status": data["status"], "modified": data["modified"]}

    async def delete_post(self, args: JSON):
        force = bool(args.get("force", False))
        await self._request("DELETE", f"{self.v2}/posts/{args['id']}", params={"force": force})
        return {"action": "deleted" if force else "trashed", "id": args["id"]}

    async def list_media(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/media", params=self._page_params(args))
        return [{"id": item["id"], "title": _rendered(item["title"]), "mime": item["mime_type"], "url": item.get("source_url", "")} for item in data]

    async def get_media(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/media/{args['id']}")
        return {"id": data["id"], "title": _rendered(data["title"]), "url": data.get("source_url", ""), "alt": data.get("alt_text", ""), "mime": data["mime_type"], "sizes": data.get("media_details", {}).get("sizes", {})}

    async def upload_media(self, args: JSON):
        content, content_type, final_url = await self.client.download_public(args["source_url"])
        filename = args.get("filename") or urlparse(final_url).path.rsplit("/", 1)[-1] or "upload"
        files = {"file": (filename, content, content_type)}
        data = await self._request("POST", f"{self.v2}/media", files=files)
        if args.get("title"):
            data = await self._request("PUT", f"{self.v2}/media/{data['id']}", json={"title": args["title"]})
        return {"id": data["id"], "title": _rendered(data["title"]), "url": data.get("source_url", "")}

    async def update_media(self, args: JSON):
        body = {key: args[key] for key in ("title", "alt_text", "caption", "description") if key in args}
        data = await self._request("PUT", f"{self.v2}/media/{args['id']}", json=body)
        return {"id": data["id"], "title": _rendered(data["title"]), "alt": data.get("alt_text", "")}

    async def delete_media(self, args: JSON):
        force = bool(args.get("force", False))
        await self._request("DELETE", f"{self.v2}/media/{args['id']}", params={"force": force})
        return {"action": "deleted" if force else "trashed", "id": args["id"]}

    async def list_users(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/users", params=self._page_params(args))
        return [{"id": user["id"], "name": user["name"], "slug": user["slug"], "roles": user.get("roles", [])} for user in data]

    async def get_user(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/users/{args['id']}")
        return {"id": data["id"], "name": data["name"], "slug": data["slug"], "avatar": data.get("avatar_urls", {}), "roles": data.get("roles", [])}

    async def get_user_me(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/users/me", params={"context": "edit"})
        return {"id": data["id"], "name": data["name"], "slug": data["slug"], "avatar": data.get("avatar_urls", {}), "roles": data.get("roles", [])}

    async def create_user(self, args: JSON):
        body = {key: args[key] for key in ("username", "password", "email", "roles") if key in args}
        data = await self._request("POST", f"{self.v2}/users", json=body)
        return {"id": data["id"], "username": data["slug"], "name": data["name"]}

    async def update_user(self, args: JSON):
        body = {key: args[key] for key in ("name", "email", "password", "roles") if key in args}
        data = await self._request("PUT", f"{self.v2}/users/{args['id']}", json=body)
        return {"id": data["id"], "name": data["name"], "roles": data.get("roles", [])}

    async def delete_user(self, args: JSON):
        if "reassign" not in args:
            raise ValidationError("reassign is required when deleting a user")
        await self._request("DELETE", f"{self.v2}/users/{args['id']}", params={"force": True, "reassign": args["reassign"]})
        return {"deleted": True, "id": args["id"], "reassign": args["reassign"]}

    async def list_comments(self, args: JSON):
        params = {"per_page": max(1, min(int(args.get("per_page", 10)), 100)), "orderby": "date", "order": "desc"}
        if "post" in args:
            params["post"] = args["post"]
        data = await self._request("GET", f"{self.v2}/comments", params=params)
        return [{"id": item["id"], "post": item.get("post", 0), "author": item.get("author_name", ""), "content": _rendered(item["content"])[:500], "status": item["status"]} for item in data]

    async def create_comment(self, args: JSON):
        body = {key: args[key] for key in ("post", "content", "parent", "author_name", "author_email") if key in args}
        data = await self._request("POST", f"{self.v2}/comments", json=body)
        return {"id": data["id"], "post": data.get("post", 0), "status": data["status"]}

    async def update_comment(self, args: JSON):
        body = {key: args[key] for key in ("content", "status") if key in args}
        data = await self._request("PUT", f"{self.v2}/comments/{args['id']}", json=body)
        return {"id": data["id"], "status": data["status"]}

    async def list_terms(self, taxonomy: str, args: JSON):
        data = await self._request("GET", f"{self.v2}/{taxonomy}", params=self._page_params(args))
        return [{"id": term["id"], "name": term["name"], "slug": term["slug"], "count": term["count"]} for term in data]

    async def create_term(self, taxonomy: str, args: JSON):
        body = {key: args[key] for key in ("name", "slug", "description") if key in args}
        data = await self._request("POST", f"{self.v2}/{taxonomy}", json=body)
        return {"id": data["id"], "name": data["name"], "slug": data["slug"]}

    async def update_category(self, args: JSON):
        body = {key: args[key] for key in ("name", "slug", "description") if key in args}
        data = await self._request("PUT", f"{self.v2}/categories/{args['id']}", json=body)
        return {"id": data["id"], "name": data["name"], "slug": data["slug"]}

    async def delete_category(self, args: JSON):
        await self._request("DELETE", f"{self.v2}/categories/{args['id']}", params={"force": True})
        return {"deleted": True, "id": args["id"]}

    async def list_menus(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/menus", params=self._page_params(args))
        return [{"id": item["id"], "name": item["name"], "slug": item["slug"]} for item in data]

    async def get_menu(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/menus/{args['id']}")
        return {"id": data["id"], "name": data["name"], "slug": data["slug"], "locations": data.get("locations", [])}

    async def create_menu(self, args: JSON):
        data = await self._request("POST", f"{self.v2}/menus", json={"name": args["name"]})
        return {"id": data["id"], "name": data["name"], "slug": data["slug"]}

    async def get_menu_items(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/menu-items", params={"menus": args["id"], **self._page_params(args)})
        return [{"id": item["id"], "title": _rendered(item["title"]), "url": item.get("url", ""), "order": item.get("menu_order", 0)} for item in data]

    async def create_menu_item(self, args: JSON):
        body = {"title": args["title"], "url": args["url"], "menus": args["menu_id"]}
        if "order" in args:
            body["menu_order"] = args["order"]
        data = await self._request("POST", f"{self.v2}/menu-items", json=body)
        return {"id": data["id"], "title": _rendered(data["title"]), "url": data.get("url", "")}

    async def get_menu_locations(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/menu-locations")
        return {key: {"name": value["name"], "menu": value.get("menu", 0)} for key, value in data.items()}

    async def get_settings(self, args: JSON):
        return await self._request("GET", f"{self.v2}/settings")

    async def update_settings(self, args: JSON):
        allowed = {"title", "description", "timezone", "date_format", "time_format", "start_of_week"}
        body = {key: value for key, value in args.items() if key in allowed}
        if not body:
            raise ValidationError("No supported setting was provided")
        return await self._request("PUT", f"{self.v2}/settings", json=body)

    async def get_site_info(self, args: JSON):
        data = await self._request("GET", "/wp-json")
        return {"name": data.get("name", ""), "description": data.get("description", ""), "url": data.get("url", ""), "namespaces": data.get("namespaces", []), "routes_count": len(data.get("routes", {}))}

    async def list_blocks(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/blocks", params=self._page_params(args))
        return [{"id": block["id"], "title": _rendered(block["title"]), "slug": block["slug"]} for block in data]

    async def get_block(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/blocks/{args['id']}", params={"context": "edit"})
        return {"id": data["id"], "title": _rendered(data["title"]), "content": data.get("content", {}).get("raw", _rendered(data.get("content")))}

    async def create_block(self, args: JSON):
        data = await self._request("POST", f"{self.v2}/blocks", json={"title": args["title"], "content": args["content"], "status": args.get("status", "publish")})
        return {"id": data["id"], "title": _rendered(data["title"])}

    async def update_block(self, args: JSON):
        body = {key: args[key] for key in ("title", "content", "status") if key in args}
        data = await self._request("PUT", f"{self.v2}/blocks/{args['id']}", json=body)
        return {"id": data["id"], "title": _rendered(data["title"])}

    async def search(self, args: JSON):
        params = {"search": args["query"], "per_page": max(1, min(int(args.get("per_page", 10)), 100))}
        if "type" in args:
            params["type"] = args["type"]
        if "subtype" in args:
            params["subtype"] = args["subtype"]
        data = await self._request("GET", f"{self.v2}/search", params=params)
        return [{"id": item["id"], "title": item["title"], "type": item.get("subtype", item.get("type", "")), "url": item.get("url", "")} for item in data]

    async def list_themes(self, args: JSON):
        data = await self._request("GET", f"{self.v2}/themes")
        return {"active": [{"name": _rendered(theme.get("name")), "version": theme.get("version", ""), "stylesheet": theme.get("stylesheet", "")} for theme in data if theme.get("status") == "active"], "available": [{"name": _rendered(theme.get("name")), "stylesheet": theme.get("stylesheet", ""), "status": theme.get("status", "")} for theme in data]}

    async def astra_settings(self):
        data = await self._request("GET", f"{self.boss}/astra-settings")
        return data.get("settings", data)

    async def astra_get_settings(self, args: JSON):
        return await self.astra_settings()

    async def astra_update_settings(self, args: JSON):
        body = {"settings": args.get("settings", {}), "merge": args.get("merge", True)}
        for key in ("menu_locations", "theme_mods"):
            if key in args:
                body[key] = args[key]
        data = await self._request("POST", f"{self.boss}/astra-settings", json=body)
        return {"success": data.get("success", False), "merged": data.get("merged", body["merge"]), "keys_updated": len(body["settings"])}

    async def astra_set_menu_location(self, args: JSON):
        return await self.astra_update_settings({"settings": {}, "merge": True, "menu_locations": {args["location"]: args["menu_id"]}})

    async def astra_get_setting(self, args: JSON):
        settings = await self.astra_settings()
        return {"key": args["key"], "present": args["key"] in settings, "value": settings.get(args["key"])}

    async def astra_get_header_builder(self, args: JSON):
        settings = await self.astra_settings()
        return {"desktop": settings.get("header-desktop-items", {}), "mobile": settings.get("header-mobile-items", {})}

    async def astra_set_header_item(self, args: JSON):
        if args["area"] not in {"desktop", "mobile"}:
            raise ValidationError("area must be desktop or mobile")
        if args["section"] not in {"primary", "above", "below"}:
            raise ValidationError("section must be primary, above, or below")
        settings = await self.astra_settings()
        key = f"header-{args['area']}-items"
        header = settings.get(key, {})
        section = header.setdefault(args["section"], {})
        section[args["slot"]] = args["items"]
        header["flag"] = True
        return await self.astra_update_settings({"settings": {key: header}, "merge": True})

    async def astra_configure_button(self, args: JSON):
        button = args["button"]
        if not button.startswith("button-") or not button.removeprefix("button-").isdigit():
            raise ValidationError("button must look like button-1")
        settings = {}
        mapping = {"text": "text", "bg_color": "back-color", "text_color": "text-color", "bg_hover_color": "back-h-color", "radius": "border-radius"}
        for source, suffix in mapping.items():
            if source in args:
                value = args[source]
                if source in {"bg_color", "text_color", "bg_hover_color"}:
                    value = {"desktop": value, "tablet": value, "mobile": value}
                settings[f"header-{button}-{suffix}"] = value
        if "url" in args:
            settings[f"header-{button}-link-option"] = {"url": args["url"], "new_tab": args.get("new_tab", ""), "link_rel": args.get("link_rel", "")}
        if "font_size" in args:
            settings[f"header-{button}-font-size"] = {"desktop": args["font_size"], "tablet": "", "mobile": "", "desktop-unit": "px", "tablet-unit": "px", "mobile-unit": "px"}
        if not settings:
            raise ValidationError("No button setting was provided")
        return await self.astra_update_settings({"settings": settings, "merge": True})

    async def astra_configure_account(self, args: JSON):
        mapping = {
            "logged_out_text": "header-account-logged-out-text",
            "logged_in_text": "header-account-logged-in-text",
            "login_style": "header-account-login-style",
            "logout_style": "header-account-logout-style",
        }
        settings = {target: args[source] for source, target in mapping.items() if source in args}
        for source, target in (("login_url", "header-account-login-link"), ("logout_url", "header-account-logout-link")):
            if source in args:
                settings[target] = {"url": args[source], "new_tab": False, "link_rel": ""}
        if not settings:
            raise ValidationError("No account setting was provided")
        return await self.astra_update_settings({"settings": settings, "merge": True})

    async def raw_request(self, args: JSON):
        endpoint = args["endpoint"]
        if not endpoint.startswith("/") or endpoint.startswith("//") or "://" in endpoint:
            raise PolicyViolation("wp_raw_request only accepts a relative /wp-json/... endpoint")
        if not endpoint.startswith("/wp-json/"):
            endpoint = f"/wp-json{endpoint}"
        method = args.get("method", "GET").upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValidationError("Unsupported HTTP method")
        kwargs = {}
        if "body" in args:
            kwargs["json"] = args["body"]
        return await self._request(method, endpoint, **kwargs)

    async def get_rest_index(self, args: JSON):
        data = await self._request("GET", "/wp-json")
        routes = {key: {"methods": value.get("methods", []), "endpoint": key} for key, value in sorted(data.get("routes", {}).items()) if not key.startswith("/oembed")}
        limit = max(1, min(int(args.get("limit", 100)), 1000))
        return {"routes_count": len(routes), "namespaces": data.get("namespaces", []), "routes": dict(list(routes.items())[:limit])}

    def specs(self) -> list[ToolSpec]:
        return _build_specs(self)


def _spec(name: str, description: str, handler: Handler, properties=None, required=None, *, read=False, destructive=False, idempotent=False, open_world=True) -> ToolSpec:
    return ToolSpec(name=name, description=description, input_schema=object_schema(properties, required), handler=handler, read_only=read, destructive=destructive, idempotent=idempotent, open_world=open_world, output_schema=OBJ)


def _build_specs(p: WordPressProvider) -> list[ToolSpec]:
    paging = {"page": INT, "per_page": INT}
    identifier = {"id": INT}
    force = {"force": BOOL}
    title_content = {"title": STR, "content": STR, "status": STR}
    specs = [
        _spec("wp_list_pages", "List WordPress pages", p.list_pages, paging, read=True),
        _spec("wp_get_page", "Get a page by ID with editable content and meta", p.get_page, {**identifier, "context": STR}, ["id"], read=True),
        _spec("wp_create_page", "Create a WordPress page", p.create_page, title_content, ["title"]),
        _spec("wp_update_page", "Update a WordPress page", p.update_page, {**identifier, **title_content, "meta": OBJ}, ["id"], idempotent=True),
        _spec("wp_delete_page", "Trash or permanently delete a WordPress page", p.delete_page, {**identifier, **force}, ["id"], destructive=True, idempotent=True),
        _spec("wp_list_posts", "List WordPress posts", p.list_posts, paging, read=True),
        _spec("wp_get_post", "Get a post by ID with editable content", p.get_post, {**identifier, "context": STR}, ["id"], read=True),
        _spec("wp_create_post", "Create a WordPress post", p.create_post, title_content, ["title"]),
        _spec("wp_update_post", "Update a WordPress post", p.update_post, {**identifier, **title_content}, ["id"], idempotent=True),
        _spec("wp_delete_post", "Trash or permanently delete a WordPress post", p.delete_post, {**identifier, **force}, ["id"], destructive=True, idempotent=True),
        _spec("wp_list_media", "List media library items", p.list_media, paging, read=True),
        _spec("wp_get_media", "Get a media item by ID", p.get_media, identifier, ["id"], read=True),
        _spec("wp_upload_media", "Upload media from a validated public URL", p.upload_media, {"source_url": STR, "title": STR, "filename": STR}, ["source_url"], open_world=True),
        _spec("wp_update_media", "Update media metadata", p.update_media, {**identifier, "title": STR, "alt_text": STR, "caption": STR, "description": STR}, ["id"], idempotent=True),
        _spec("wp_delete_media", "Trash or permanently delete media", p.delete_media, {**identifier, **force}, ["id"], destructive=True, idempotent=True),
        _spec("wp_list_users", "List WordPress users", p.list_users, paging, read=True),
        _spec("wp_get_user", "Get a WordPress user", p.get_user, identifier, ["id"], read=True),
        _spec("wp_get_user_me", "Get the authenticated WordPress user", p.get_user_me, {}, read=True),
        _spec("wp_create_user", "Create a WordPress user", p.create_user, {"username": STR, "password": STR, "email": STR, "roles": STRINGS}, ["username", "password"], destructive=True),
        _spec("wp_update_user", "Update a WordPress user", p.update_user, {**identifier, "name": STR, "email": STR, "password": STR, "roles": STRINGS}, ["id"], destructive=True, idempotent=True),
        _spec("wp_delete_user", "Permanently delete a user and reassign content", p.delete_user, {**identifier, "reassign": INT}, ["id", "reassign"], destructive=True, idempotent=True),
        _spec("wp_list_comments", "List recent comments", p.list_comments, {"post": INT, "per_page": INT}, read=True),
        _spec("wp_create_comment", "Create a comment", p.create_comment, {"post": INT, "content": STR, "parent": INT, "author_name": STR, "author_email": STR}, ["post", "content"]),
        _spec("wp_update_comment", "Update or moderate a comment", p.update_comment, {**identifier, "content": STR, "status": STR}, ["id"], destructive=True, idempotent=True),
        _spec("wp_list_categories", "List categories", lambda a: p.list_terms("categories", a), paging, read=True),
        _spec("wp_create_category", "Create a category", lambda a: p.create_term("categories", a), {"name": STR, "slug": STR, "description": STR}, ["name"]),
        _spec("wp_update_category", "Update a category", p.update_category, {**identifier, "name": STR, "slug": STR, "description": STR}, ["id"], idempotent=True),
        _spec("wp_delete_category", "Delete a category", p.delete_category, identifier, ["id"], destructive=True, idempotent=True),
        _spec("wp_list_tags", "List tags", lambda a: p.list_terms("tags", a), paging, read=True),
        _spec("wp_create_tag", "Create a tag", lambda a: p.create_term("tags", a), {"name": STR, "slug": STR, "description": STR}, ["name"]),
        _spec("wp_list_menus", "List navigation menus", p.list_menus, paging, read=True),
        _spec("wp_get_menu", "Get a navigation menu", p.get_menu, identifier, ["id"], read=True),
        _spec("wp_create_menu", "Create a navigation menu", p.create_menu, {"name": STR}, ["name"]),
        _spec("wp_get_menu_items", "Get items in a navigation menu", p.get_menu_items, {**identifier, **paging}, ["id"], read=True),
        _spec("wp_create_menu_item", "Add an item to a navigation menu", p.create_menu_item, {"title": STR, "url": STR, "menu_id": INT, "order": INT}, ["title", "url", "menu_id"]),
        _spec("wp_get_menu_locations", "Get registered navigation menu locations", p.get_menu_locations, {}, read=True),
        _spec("wp_get_settings", "Get site settings", p.get_settings, {}, read=True),
        _spec("wp_update_settings", "Update supported site settings", p.update_settings, {"title": STR, "description": STR, "timezone": STR, "date_format": STR, "time_format": STR, "start_of_week": INT}, idempotent=True),
        _spec("wp_get_site_info", "Get WordPress site and REST namespace information", p.get_site_info, {}, read=True),
        _spec("wp_list_blocks", "List reusable blocks", p.list_blocks, paging, read=True),
        _spec("wp_get_block", "Get editable reusable block content", p.get_block, identifier, ["id"], read=True),
        _spec("wp_create_block", "Create a reusable block", p.create_block, title_content, ["title", "content"]),
        _spec("wp_update_block", "Update a reusable block", p.update_block, {**identifier, **title_content}, ["id"], idempotent=True),
        _spec("wp_search", "Search WordPress content", p.search, {"query": STR, "type": STR, "subtype": STR, "per_page": INT}, ["query"], read=True),
        _spec("wp_list_themes", "List installed WordPress themes", p.list_themes, {}, read=True),
        _spec("wp_astra_get_settings", "Get all Astra settings", p.astra_get_settings, {}, read=True),
        _spec("wp_astra_update_settings", "Merge or replace Astra settings", p.astra_update_settings, {"settings": OBJ, "merge": BOOL, "menu_locations": OBJ, "theme_mods": OBJ}, ["settings"], idempotent=True),
        _spec("wp_astra_set_menu_location", "Assign a menu to an Astra location", p.astra_set_menu_location, {"menu_id": INT, "location": STR}, ["menu_id", "location"], idempotent=True),
        _spec("wp_astra_get_setting", "Get one Astra setting", p.astra_get_setting, {"key": STR}, ["key"], read=True),
        _spec("wp_astra_get_header_builder", "Get Astra desktop and mobile header layouts", p.astra_get_header_builder, {}, read=True),
        _spec("wp_astra_set_header_item", "Set components in an Astra header slot", p.astra_set_header_item, {"area": {"type": "string", "enum": ["desktop", "mobile"]}, "section": {"type": "string", "enum": ["primary", "above", "below"]}, "slot": STR, "items": STRINGS}, ["area", "section", "slot", "items"], idempotent=True),
        _spec("wp_astra_configure_button", "Configure an Astra header button", p.astra_configure_button, {"button": STR, "text": STR, "url": STR, "bg_color": STR, "text_color": STR, "bg_hover_color": STR, "radius": STR, "font_size": STR, "new_tab": STR, "link_rel": STR}, ["button"], idempotent=True),
        _spec("wp_astra_configure_account", "Configure the Astra account widget", p.astra_configure_account, {"logged_out_text": STR, "logged_in_text": STR, "login_url": STR, "logout_url": STR, "login_style": STR, "logout_style": STR}, idempotent=True),
        _spec("wp_raw_request", "Make an authenticated request to a relative WordPress REST endpoint", p.raw_request, {"endpoint": STR, "method": STR, "body": OBJ}, ["endpoint"], destructive=True),
        _spec("wp_get_rest_index", "List WordPress REST routes", p.get_rest_index, {"limit": INT}, read=True),
    ]
    return specs
