"""Page awareness: Nouri knows every major DoGoods route."""

from backend.ai.conversation_flow import (
    build_live_guide_prompt,
    build_page_knowledge_prompt,
    _page_already_open,
    _page_key_from_path,
)
from backend.ai.tools import _NAV_TARGET_PATHS, _NAV_TARGET_LABELS


def test_page_key_from_common_paths():
    assert _page_key_from_path("/") == "home"
    assert _page_key_from_path("/share") == "share"
    assert _page_key_from_path("/find") == "find"
    assert _page_key_from_path("/near-me") == "near-me"
    assert _page_key_from_path("/request") == "request"
    assert _page_key_from_path("/claim") == "claim"
    assert _page_key_from_path("/profile") == "profile"
    assert _page_key_from_path("/settings") == "settings"
    assert _page_key_from_path("/receipts") == "receipts"
    assert _page_key_from_path("/community/abc") == "community"
    assert _page_key_from_path("/admin/share-food") == "admin"


def test_page_knowledge_covers_core_flows():
    for key in ("share", "find", "request", "claim", "profile", "settings", "home"):
        prompt = build_page_knowledge_prompt({"pageKey": key, "path": f"/{key}" if key != "home" else "/"})
        assert prompt
        assert "PAGE KNOWLEDGE" in prompt or key == "home"
        assert "navigate_ui" in prompt.lower() or "Find" in prompt or "Share" in prompt


def test_live_guide_includes_page_key():
    prompt = build_live_guide_prompt({
        "path": "/settings",
        "pageKey": "settings",
        "formId": None,
        "fieldName": "",
    })
    assert prompt
    assert "settings" in prompt.lower()
    assert "/settings" in prompt


def test_page_already_open_uses_page_key():
    assert _page_already_open({"pageKey": "share", "path": "/share"}, "share")
    assert _page_already_open({"pageKey": "find", "path": "/find"}, "find")
    assert _page_already_open({"pageKey": "near-me", "path": "/near-me"}, "find")
    assert not _page_already_open({"pageKey": "home", "path": "/"}, "share")


def test_nav_targets_include_core_product_pages():
    for target, path in {
        "create": "/share",
        "list": "/find",
        "request": "/request",
        "claim": "/claim",
        "profile": "/profile",
        "settings": "/settings",
        "receipts": "/receipts",
        "listings": "/listings",
        "near-me": "/near-me",
        "login": "/login",
        "signup": "/signup",
        "home": "/",
        "partners": "/sponsors",
    }.items():
        assert target in _NAV_TARGET_LABELS
        assert _NAV_TARGET_PATHS[target] == path
