"""Tests for quick-reply chip suggestions returned by the AI."""
from backend.ai.ai_engine import generate_quick_replies


def test_no_question_returns_empty():
    assert generate_quick_replies("Posted! Listing #42 is live.") == []
    assert generate_quick_replies("") == []


def test_open_what_food_question_suggests_food_options():
    out = generate_quick_replies("What food would you like to share today?")
    # Should NOT be yes/no/later — that was the old bug.
    assert "Yes" not in out and "No" not in out and "Later" not in out
    assert len(out) >= 2
    # Plausible food chips
    joined = " ".join(out).lower()
    assert any(x in joined for x in ("bread", "fruit", "vegetable", "meal"))


def test_open_wh_question_without_specific_branch_returns_empty():
    # Open question we have no concrete suggestions for — better empty
    # than wrong yes/no chips.
    out = generate_quick_replies("What neighborhood are you in?")
    assert out == []


def test_post_confirm_variants():
    confirm_phrasings = [
        "Quick check — 3 loaves of sourdough, pickup at 1423 Park St. Post it?",
        "Sound good? Should I post it?",
        "Ready to post?",
        "All set — shall I publish it?",
        "Looks good? Confirm and post?",
        "Want me to post the listing?",
    ]
    for q in confirm_phrasings:
        out = generate_quick_replies(q)
        assert out, f"no chips for: {q!r}"
        joined = " ".join(out).lower()
        assert "post" in joined or "edit" in joined or "cancel" in joined, (
            f"wrong chips for {q!r}: {out}"
        )
        # Must NOT fall through to bare yes/no/later
        assert out[:3] != ["Yes", "No", "Later"], f"fell through on: {q!r}"


def test_post_confirm_spanish():
    out = generate_quick_replies("¿Lo publico?", lang="es")
    assert out
    assert any("public" in s.lower() or "publí" in s.lower() for s in out)


def test_handoff_question_gets_handoff_chips():
    out = generate_quick_replies(
        "Will the recipient pick this up from you, or are you willing to drop it off?"
    )
    assert out
    joined = " ".join(out).lower()
    assert "pickup" in joined or "drop" in joined or "either" in joined


def test_address_confirm_gets_address_chips():
    out = generate_quick_replies(
        "Should I use your profile address 1423 Park St for the pickup spot?"
    )
    assert out
    joined = " ".join(out).lower()
    assert "address" in joined or "profile" in joined or "use that" in joined


def test_quantity_question_gets_numbers():
    out = generate_quick_replies("How many loaves?")
    assert out
    assert any(s.isdigit() for s in out)


def test_allergen_question():
    out = generate_quick_replies("Any allergens I should flag?")
    assert out
    joined = " ".join(out).lower()
    assert "allergen" in joined or "gluten" in joined or "dairy" in joined


def test_yes_no_fallback_only_when_truly_yes_no():
    out = generate_quick_replies("Would you like me to remind you tomorrow?")
    # "Would you like" with no open-wh and no specific branch → yes/no/later.
    assert "Yes" in out and "No" in out


def test_help_menu_does_not_get_claim_pick_chips():
    """Regression: orientation menus used to emit 1/2/3 + easy-to-prepare."""
    out = generate_quick_replies(
        "You can find free food near you, check pickups, or see events. "
        "Which one would you like to try first?"
    )
    assert "Something easy to prepare" not in out
    assert "1" not in out
    joined = " ".join(out).lower()
    assert "find" in joined or "share" in joined or "pickup" in joined


def test_real_search_results_still_get_pick_chips():
    out = generate_quick_replies(
        "Here's what's close near you: 1. Bread 2. Apples. Which one would you like?"
    )
    assert "1" in out
    assert "Something easy to prepare" in out


# ---------------------------------------------------------------------------
# Spanish coverage — every English branch must have a working ES counterpart.
# ---------------------------------------------------------------------------


def test_es_no_question_returns_empty():
    assert generate_quick_replies("¡Listo! Publicación #42 en vivo.", lang="es") == []


def test_es_what_food_question_suggests_food_options():
    cases = [
        "¿Qué comida quieres compartir hoy?",
        "¿Qué te gustaría donar?",
        "¿Qué tipo de comida tienes?",
        "¿Qué vas a compartir?",
    ]
    for q in cases:
        out = generate_quick_replies(q, lang="es")
        assert out, f"no chips for: {q!r}"
        # Must not be yes/no fallback
        assert "Sí" not in out or "No" not in out or "Más tarde" not in out, (
            f"fell through to yes/no on: {q!r}"
        )
        joined = " ".join(out).lower()
        assert any(x in joined for x in ("pan", "frut", "verdur", "comida"))


def test_es_post_confirm_variants():
    confirm_phrasings = [
        "Resumen rápido — 3 panes, recogida en tu casa. ¿Lo publico?",
        "¿Lo publicamos?",
        "¿Listo para publicar?",
        "¿Está bien así? ¿Publicarlo?",
        "¿Confirmas y publico?",
    ]
    for q in confirm_phrasings:
        out = generate_quick_replies(q, lang="es")
        assert out, f"no chips for: {q!r}"
        joined = " ".join(out).lower()
        assert any(x in joined for x in ("publí", "edít", "cancel")), (
            f"wrong chips for {q!r}: {out}"
        )


def test_es_handoff_question():
    out = generate_quick_replies(
        "¿Lo van a recoger en tu casa, o tú lo entregas?", lang="es"
    )
    assert out
    joined = " ".join(out).lower()
    assert "recog" in joined or "entreg" in joined or "cualquiera" in joined


def test_es_address_confirm():
    out = generate_quick_replies(
        "¿Uso la dirección de tu perfil 1423 Park St?", lang="es"
    )
    assert out
    joined = " ".join(out).lower()
    assert "direcci" in joined or "usa esa" in joined


def test_es_quantity_question():
    out = generate_quick_replies("¿Cuántos panes?", lang="es")
    assert out
    assert any(s.isdigit() for s in out)


def test_es_allergen_question():
    out = generate_quick_replies("¿Algún alérgeno?", lang="es")
    assert out
    joined = " ".join(out).lower()
    assert "alérgeno" in joined or "gluten" in joined or "lácteo" in joined


def test_es_pickup_window():
    out = generate_quick_replies("¿Cuándo pueden recogerlo?", lang="es")
    assert out
    joined = " ".join(out).lower()
    assert "hoy" in joined or "mañana" in joined or "24h" in joined


def test_es_freshness_question():
    out = generate_quick_replies("¿Cuándo se horneó? ¿Vence pronto?", lang="es")
    assert out
    joined = " ".join(out).lower()
    assert "hecho" in joined or "vence" in joined


def test_es_photo_question():
    out = generate_quick_replies("¿Puedes mandar una foto?", lang="es")
    assert out
    joined = " ".join(out).lower()
    assert "foto" in joined or "después" in joined


def test_es_yes_no_fallback():
    out = generate_quick_replies("¿Quieres que te recuerde mañana?", lang="es")
    # Generic yes/no in Spanish
    assert "Sí" in out and "No" in out


def test_foolproof_help_menu_chips():
    out = generate_quick_replies("What can you do? I'm not sure where to start.")
    assert len(out) >= 3
    joined = " ".join(out).lower()
    assert "food" in joined
    assert "request" in joined or "share" in joined


def test_foolproof_share_starter_chips():
    out = generate_quick_replies("What food and how much would you like to share?")
    assert len(out) >= 2
    joined = " ".join(out).lower()
    assert "apple" in joined or "bread" in joined or "vegetable" in joined or "egg" in joined


def test_foolproof_combined_food_qty_chips():
    out = generate_quick_replies("What food and how much do you have?")
    assert len(out) >= 2
    joined = " ".join(out).lower()
    assert "apple" in joined or "bread" in joined or "egg" in joined


def test_community_confirm_shows_suggested_and_different():
    out = generate_quick_replies(
        "Which school should this go under — Alameda Unified School District?",
        suggested_community="Alameda Unified School District",
    )
    assert "Alameda Unified School District" in out
    assert "Different one" in out


def test_community_confirm_spanish():
    out = generate_quick_replies(
        "¿Bajo qué comunidad debo publicarlo — Distrito Escolar de Alameda?",
        lang="es",
        suggested_community="Distrito Escolar de Alameda",
    )
    assert "Distrito Escolar de Alameda" in out
    assert "Otra comunidad" in out


def test_different_one_shows_other_communities():
    schools = [
        "Alameda Unified School District",
        "Oakland Unified School District",
        "Berkeley Unified School District",
    ]
    out = generate_quick_replies(
        "Which community would you like?",
        user_message="Different one",
        communities=schools,
        suggested_community="Alameda Unified School District",
    )
    assert "Oakland Unified School District" in out
    assert "Berkeley Unified School District" in out
    assert "Alameda Unified School District" not in out


def test_food_insecurity_user_message_starter_chips():
    out = generate_quick_replies(
        "",
        user_message="I'm a single mother and we have nothing to eat",
    )
    assert len(out) >= 2
    joined = " ".join(out).lower()
    assert "food" in joined or "comida" in joined


def test_food_option_picker_chips():
    out = generate_quick_replies(
        "Here are the closest options near you:\n"
        "1. Bread — 0.4 mi\n2. Vegetables — 0.7 mi\n"
        "Which one would you like to claim? Reply with the number or name.",
    )
    assert "1" in out
    assert any("closest" in s.lower() or "easy" in s.lower() for s in out)


def test_homebound_mobility_chips():
    out = generate_quick_replies(
        "I found a few options — can you pick them up, or do you need help getting there?",
        user_message="I can't walk, I've been in the house",
    )
    assert out
    joined = " ".join(out).lower()
    assert "delivery" in joined or "closest" in joined or "request" in joined

