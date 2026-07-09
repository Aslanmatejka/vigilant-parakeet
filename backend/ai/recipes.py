"""Recipe generation for FoodCard, RecipesPage, and get_recipes tool."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from backend.ai.ai_engine import CHAT_MODEL, _extract_content, legacy_ai_request

logger = logging.getLogger("ai_recipes")


def _parse_json_array(text: str) -> list[Any]:
    """Best-effort parse of a JSON array from an LLM reply."""
    if not text or not str(text).strip():
        return []
    raw = str(text).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("["), raw.rfind("]")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return []
        else:
            return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("recipes", "items", "results", "data"):
            val = parsed.get(key)
            if isinstance(val, list):
                return val
    return []


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("item") or item.get("ingredient")
                qty = item.get("quantity") or item.get("qty") or item.get("amount")
                if name:
                    out.append(f"{qty} {name}".strip() if qty else str(name))
        return out
    return []


def _minutes_from_recipe(raw: dict) -> Optional[int]:
    for key in ("time_minutes", "total_time_minutes", "total_time"):
        val = raw.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
        if isinstance(val, str):
            m = re.search(r"(\d+)", val)
            if m:
                return int(m.group(1))
    prep = raw.get("prep_time") or raw.get("prepTime") or ""
    cook = raw.get("cook_time") or raw.get("cookTime") or ""
    total = 0
    for part in (prep, cook):
        if isinstance(part, (int, float)):
            total += int(part)
        elif isinstance(part, str):
            m = re.search(r"(\d+)", part)
            if m:
                total += int(m.group(1))
    return total or None


def _normalize_recipe(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {
            "title": str(raw or "Recipe"),
            "summary": "",
            "ingredients": [],
            "steps": [],
            "servings": 2,
            "time_minutes": None,
            "difficulty": "easy",
            "cost_tier": "low",
            "dietary_tags": [],
        }
    title = (
        raw.get("title")
        or raw.get("name")
        or raw.get("recipe_name")
        or "Recipe"
    )
    steps = _as_str_list(raw.get("steps") or raw.get("instructions") or raw.get("directions"))
    if not steps and isinstance(raw.get("instructions"), str):
        steps = [s.strip() for s in raw["instructions"].split("\n") if s.strip()]
    ingredients = _as_str_list(
        raw.get("ingredients") or raw.get("ingredient_list") or raw.get("items")
    )
    servings = raw.get("servings") or raw.get("serves")
    try:
        servings = int(servings) if servings is not None else 2
    except (TypeError, ValueError):
        servings = 2
    difficulty = str(raw.get("difficulty") or "easy").strip().lower() or "easy"
    cost = str(raw.get("cost_tier") or raw.get("cost") or "low").strip().lower()
    if cost not in {"low", "medium", "high"}:
        cost = "low"
    summary = str(raw.get("summary") or raw.get("description") or "").strip()
    if not summary and steps:
        summary = steps[0][:160]
    return {
        "title": str(title).strip() or "Recipe",
        "summary": summary,
        "ingredients": ingredients,
        "steps": steps,
        "servings": max(1, servings),
        "time_minutes": _minutes_from_recipe(raw),
        "difficulty": difficulty,
        "cost_tier": cost,
        "dietary_tags": _as_str_list(raw.get("dietary_tags") or raw.get("tags")),
    }


async def _load_user_recipe_context(user_id: str) -> dict:
    from backend.ai_engine import supabase_get

    ctx: dict = {
        "household_size": None,
        "dietary_restrictions": [],
        "allergies": [],
    }
    try:
        rows = await supabase_get("users", {
            "id": f"eq.{user_id}",
            "select": "household_size,dietary_restrictions,allergies",
        })
        if not rows:
            return ctx
        row = rows[0]
        ctx["household_size"] = row.get("household_size")
        for field in ("dietary_restrictions", "allergies"):
            raw = row.get(field)
            if isinstance(raw, list):
                ctx[field] = [str(x).strip() for x in raw if x]
            elif isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        ctx[field] = [str(x).strip() for x in parsed if x]
                    else:
                        ctx[field] = [raw.strip()]
                except (ValueError, TypeError):
                    ctx[field] = [p.strip() for p in raw.split(",") if p.strip()]
    except Exception as exc:
        logger.warning("recipe user context lookup failed: %s", exc)
    return ctx


async def _load_claimed_ingredients(user_id: str, limit: int = 10) -> list[str]:
    from backend.ai_engine import supabase_get

    titles: list[str] = []
    try:
        claims = await supabase_get("food_claims", {
            "claimer_id": f"eq.{user_id}",
            "status": "in.(pending,approved)",
            "select": "food_id",
            "limit": str(limit),
        })
        food_ids = [c["food_id"] for c in claims if c.get("food_id")]
        for fid in food_ids[:limit]:
            rows = await supabase_get("food_listings", {
                "id": f"eq.{fid}",
                "select": "title,category",
            })
            if rows:
                title = (rows[0].get("title") or "").strip()
                if title and title not in titles:
                    titles.append(title)
    except Exception as exc:
        logger.warning("claimed ingredients lookup failed: %s", exc)
    return titles


async def generate_recipes(
    *,
    user_id: Optional[str] = None,
    ingredients: Optional[list[str]] = None,
    use_claimed: bool = True,
    low_resource: bool = True,
    household_size: Optional[int] = None,
    max_recipes: int = 3,
    dietary_overrides: Optional[list[str]] = None,
    notes: Optional[str] = None,
) -> dict:
    """Generate structured recipe suggestions for the UI and get_recipes tool."""
    max_recipes = max(1, min(int(max_recipes or 3), 5))
    ingredient_list = [str(i).strip() for i in (ingredients or []) if str(i).strip()]
    source = "explicit"

    profile = await _load_user_recipe_context(user_id) if user_id else {
        "household_size": None,
        "dietary_restrictions": [],
        "allergies": [],
    }
    if household_size is None and profile.get("household_size"):
        try:
            household_size = int(profile["household_size"])
        except (TypeError, ValueError):
            household_size = 2
    household_size = max(1, min(int(household_size or 2), 20))

    diet_parts = list(profile.get("dietary_restrictions") or [])
    if dietary_overrides:
        diet_parts.extend(str(d).strip() for d in dietary_overrides if str(d).strip())
    diet_parts = list(dict.fromkeys(diet_parts))
    allergies = list(dict.fromkeys(profile.get("allergies") or []))

    if not ingredient_list and use_claimed and user_id:
        ingredient_list = await _load_claimed_ingredients(user_id)
        if ingredient_list:
            source = "claimed"

    if not ingredient_list:
        source = "pantry"
        ingredient_list = ["common pantry staples"]

    diet_note = f" Dietary requirements: {', '.join(diet_parts)}." if diet_parts else ""
    allergy_note = (
        f" Strictly avoid allergens: {', '.join(allergies)}."
        if allergies else ""
    )
    hh_note = f" Scale for a household of {household_size}."
    low_note = (
        " Use a LOW-RESOURCE kitchen: one pot/stovetop, minimal equipment, "
        "budget-friendly staples."
        if low_resource else ""
    )
    notes_note = f" Extra notes: {notes.strip()}." if notes and notes.strip() else ""

    prompt = (
        f"Create exactly {max_recipes} practical recipes using: "
        f"{', '.join(ingredient_list)}.{diet_note}{allergy_note}{hh_note}{low_note}{notes_note} "
        'Return a JSON object with a single key "recipes" whose value is an array. '
        "Each recipe object must include: "
        "title, summary (1 sentence), ingredients (array of strings with quantities), "
        "steps (array of short strings), servings (integer), time_minutes (integer), "
        "difficulty (easy|medium|hard), cost_tier (low|medium|high), "
        "dietary_tags (array of strings)."
    )

    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful culinary assistant for a food-sharing community. "
                    "Return valid JSON arrays only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }

    try:
        data = await legacy_ai_request("/chat/completions", payload)
        content = _extract_content(data)
        parsed = _parse_json_array(content)
        if not parsed and content.strip().startswith("{"):
            try:
                wrapper = json.loads(content)
                parsed = _parse_json_array(json.dumps(wrapper))
            except json.JSONDecodeError:
                parsed = []
    except Exception as exc:
        logger.error("generate_recipes LLM call failed: %s", exc)
        return {"error": f"Failed to generate recipes: {exc}"}

    recipes = [_normalize_recipe(r) for r in parsed[:max_recipes]]
    if not recipes and parsed:
        recipes = [_normalize_recipe(parsed[0])]

    if ingredient_list == ["common pantry staples"]:
        headline = "Easy pantry-friendly ideas"
    elif source == "claimed":
        headline = f"Recipes using your claimed food ({len(ingredient_list)} items)"
    else:
        headline = f"Recipe ideas for {', '.join(ingredient_list[:3])}"

    if not recipes:
        return {
            "headline": "No recipes generated — try different ingredients.",
            "recipes": [],
            "source": source,
            "ingredients_used": ingredient_list,
            "household_size": household_size,
            "low_resource": low_resource,
            "dietary_restrictions": diet_parts,
            "allergens_avoided": allergies,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "headline": headline,
        "recipes": recipes,
        "source": source,
        "ingredients_used": ingredient_list,
        "household_size": household_size,
        "low_resource": low_resource,
        "dietary_restrictions": diet_parts,
        "allergens_avoided": allergies,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
