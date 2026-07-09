"""Tests for recipe parsing and generation helpers."""
import json

from backend.ai.recipes import _normalize_recipe, _parse_json_array


def test_parse_json_array_from_fence():
    raw = '```json\n[{"title": "Soup"}]\n```'
    assert len(_parse_json_array(raw)) == 1


def test_parse_json_object_wrapper():
    raw = json.dumps({"recipes": [{"title": "Toast", "steps": ["Toast bread"]}]})
    parsed = _parse_json_array(raw)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Toast"


def test_normalize_recipe_maps_fields():
    item = _normalize_recipe({
        "name": "Bean stew",
        "ingredients": ["1 can beans", "rice"],
        "instructions": ["Heat", "Serve"],
        "servings": 4,
        "prep_time": "10 min",
        "cook_time": "20 min",
        "difficulty": "Easy",
        "cost_tier": "low",
    })
    assert item["title"] == "Bean stew"
    assert len(item["ingredients"]) == 2
    assert len(item["steps"]) == 2
    assert item["servings"] == 4
    assert item["time_minutes"] == 30
