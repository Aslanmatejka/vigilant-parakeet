"""Tests for quick-reply chip suggestions returned by the AI."""
from backend.ai.ai_engine import generate_quick_replies


def test_no_question_returns_empty():
    # Bare status with no next ask — still OK to offer light next-steps.
    out = generate_quick_replies("Posted! Listing #42 is live.")
    assert "Yes" not in out and "Later" not in out
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
        "Quick check — 3 loaves of sourdough, pickup at 1423 Park St, with your photos. Post it?",
        "Sound good? Should I post it? Photos received.",
        "Ready to post with your photos?",
        "All set — shall I publish it? Photo attached.",
        "Looks good? Confirm and post? Got your photo.",
        "Want me to post the listing? Photos received.",
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
    out = generate_quick_replies("Foto adjunta. ¿Lo publico?", lang="es")
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
        "Should I use your profile address 1423 Park St for the pickup spot?",
        suggested_community="Alameda Unified",
    )
    assert out
    joined = " ".join(out).lower()
    assert "address" in joined or "use that one" in joined or "saved" in joined
    assert "Alameda Unified" not in out
    assert "Different one" not in out
    assert "Yes, post it" not in out


def test_quantity_question_gets_numbers():
    out = generate_quick_replies("How many loaves?")
    assert out
    assert any(s.isdigit() for s in out)
    assert "All of them" not in out
    assert out == ["1", "3", "5", "10"] or set(out) >= {"1", "3", "5"}


def test_allergen_question():
    out = generate_quick_replies("Any allergens I should flag?")
    assert out
    joined = " ".join(out).lower()
    assert "allergen" in joined or "gluten" in joined or "dairy" in joined


def test_yes_no_fallback_only_when_truly_yes_no():
    out = generate_quick_replies("Would you like me to remind you tomorrow?")
    assert "Yes, remind me" in out
    assert "Yes" not in out or out[0] != "Yes"
    assert "Later" not in out


def test_ambiguous_would_you_like_returns_empty_not_yes_no():
    """Regression: polite 'would you like' must not become Yes/No/Later."""
    out = generate_quick_replies(
        "Would you like me to open Find Food, or help another way?"
    )
    assert out[:3] != ["Yes", "No", "Later"]
    # Prefer fork chips or empty — never bare Yes/No.
    assert "Later" not in out


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
    out = generate_quick_replies("¡Listo! Publicación #42 en vivo.", lang="es")
    assert "Más tarde" not in out
    assert "Sí" not in out or any("compart" in s.lower() or "buscar" in s.lower() or "todo" in s.lower() for s in out)


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
        "Resumen rápido — 3 panes, recogida en tu casa, foto adjunta. ¿Lo publico?",
        "Fotos recibidas. ¿Lo publicamos?",
        "¿Listo para publicar? Foto adjunta.",
        "¿Está bien así? ¿Publicarlo? Foto adjunta.",
        "¿Confirmas y publico? Foto adjunta.",
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
    out = generate_quick_replies(
        "¿Hasta cuándo es bueno? ¿Fecha de vencimiento?", lang="es",
    )
    assert out
    joined = " ".join(out).lower()
    assert "mañana" in joined or "días" in joined
    assert "en un mes" in joined
    assert "hecho hoy" not in joined
    assert "hecho ayer" not in joined
    assert "bueno 24" not in joined


def test_good_until_chips_not_made_today():
    out = generate_quick_replies(
        "When is this food good until? Best-by or use-by date?",
    )
    assert "Tomorrow" in out
    assert "In 2 days" in out
    assert "In a month" in out
    assert "Good for 24 hours" not in out
    assert "Made today" not in out
    assert "Made yesterday" not in out


def test_expiry_chips_without_question_mark():
    out = generate_quick_replies("When does it expire")
    assert "Tomorrow" in out
    assert "In 2 days" in out
    assert "In a month" in out


def test_expiry_chips_when_school_also_mentioned():
    out = generate_quick_replies(
        "I'll list this under Alameda Unified School District. "
        "When does it expire?"
    )
    assert "Tomorrow" in out
    assert "Do it for me" not in out


def test_allergen_ask_not_expiry_chips():
    """Allergen question must not keep showing best-by date chips."""
    out = generate_quick_replies(
        "Got it — best by tomorrow. Any allergens in the pizza, "
        "like nuts, dairy, eggs, wheat, soy, or shellfish?",
    )
    assert "No allergens" in out
    assert "Tomorrow" not in out
    assert "In 2 days" not in out
    assert "Other date" not in out


def test_expiry_ack_does_not_reoffer_date_chips():
    out = generate_quick_replies(
        "Got it — best by tomorrow. I'll note that.",
    )
    assert "Tomorrow" not in out
    assert "In 2 days" not in out


def test_fresh_food_question_does_not_get_expiry_chips():
    out = generate_quick_replies(
        "What fresh food are you sharing today?",
    )
    joined = " ".join(out).lower()
    assert "made today" not in joined
    assert "in 2 days" not in joined
    assert "good for 24" not in joined


def test_es_photo_question():
    out = generate_quick_replies("¿Puedes mandar una foto?", lang="es")
    assert out
    joined = " ".join(out).lower()
    assert "foto" in joined or "adjunt" in joined
    assert "sin foto" not in joined


def test_es_yes_no_fallback():
    out = generate_quick_replies("¿Quieres que te recuerde mañana?", lang="es")
    joined = " ".join(out).lower()
    assert "recuer" in joined.replace("é", "e").replace("á", "a")
    assert "Más tarde" not in out
    assert out[:3] != ["Sí", "No", "Más tarde"]


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


def test_hands_on_food_and_how_much_not_bare_qty():
    """Do-it-for-me opener must get food+qty examples, not 1/3/5/10."""
    out = generate_quick_replies(
        "You got it! What food do you want to share, and how much do you have?",
        user_message="Do it for me",
    )
    assert out
    assert out != ["1", "3", "5", "10"]
    joined = " ".join(out).lower()
    assert "apple" in joined or "bread" in joined or "vegetable" in joined or "egg" in joined


def test_hands_on_qty_after_food_known():
    out = generate_quick_replies(
        "Yum, pizza! How many slices or whole pizzas are you sharing?",
        user_message="pizza",
    )
    assert out == ["1", "3", "5", "10"] or set(out) >= {"1", "3", "5"}


def test_hands_on_community_confirm_and_pick():
    out = generate_quick_replies(
        "Should I post this under Alameda Unified School District, since that is your community?",
        suggested_community="Alameda Unified School District",
    )
    assert "Alameda Unified School District" in out
    assert "Different one" in out

    pick = generate_quick_replies(
        "Got it, you want to post your pizza in a different community. Which community should I use?",
        user_message="Different one",
        communities=["NEA/ACLC CC", "Do Good Warehouse", "Ruby Bridges Elementary CC"],
    )
    assert "NEA/ACLC CC" in pick
    assert "Do Good Warehouse" in pick


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


def test_guided_without_question_mark_gets_done_chips():
    out = generate_quick_replies(
        "GUIDED — STEP 1 of 9 (SHARE FOOD):\n"
        "Click Name / Organization and type your name. Say done when finished."
    )
    assert "Done" in out
    assert "What's next?" in out
    assert "Yes" not in out


def test_community_ask_does_not_return_post_chips():
    out = generate_quick_replies(
        "Which community should I list the 10 loaves under? "
        "Your profile is set to Alameda Unified—should I post it there?"
    )
    assert "Yes, post it" not in out
    joined = " ".join(out).lower()
    assert "community" in joined or "different" in joined or "profile" in joined


def test_ready_to_claim_not_generic_yes_no():
    out = generate_quick_replies("Ready to claim these? 2 bread and 3 apples.")
    assert "Yes, claim these" in out
    assert out[:3] != ["Yes", "No", "Later"]


def test_claim_listing_yes_no_is_ok():
    out = generate_quick_replies("Would you like me to claim this listing for you?")
    assert "Yes, claim it" in out
    assert "Later" not in out
    assert out[:3] != ["Yes", "No", "Later"]


def test_photo_ask_never_offers_skip_chip():
    for text in (
        "Please attach a photo of the food — required before I can post.",
        "Want to snap a quick photo of the tomatoes or carrots, or skip the photos?",
        "Can I post without a photo?",
    ):
        out = generate_quick_replies(text, user_message="share food")
        joined = " ".join(out).lower()
        assert "skip" not in joined, (text, out)
        assert "without" not in joined, (text, out)
        assert out[:3] != ["Yes", "No", "Later"]


def test_vague_share_proceed_gets_fork_not_yes_no():
    out = generate_quick_replies(
        "How would you like to proceed with sharing?"
    )
    assert "Open the form" in out
    assert "Do it for me" in out
    assert "Guide me step by step" in out
    assert "Yes" not in out


def test_shall_i_claim_single_not_multi():
    out = generate_quick_replies("Shall I claim listing #12 for you?")
    assert "Yes, claim it" in out
    assert "Yes, claim these" not in out


def test_find_food_fork_not_yes_no():
    out = generate_quick_replies(
        "I can search nearby. Want me to handle the search for you, "
        "or guide you on Find Food step by step?"
    )
    assert "Open Find Food" in out
    assert "Open the form" not in out
    assert "Do it for me" in out
    assert "Guide me step by step" in out
    assert out[:3] != ["Yes", "No", "Later"]


def test_find_food_fork_omits_open_when_already_on_find():
    from backend.agent.suggestion_chips import share_assistance_fork_chips

    chips = share_assistance_fork_chips(
        "Want me to handle the search, or guide you step by step on Find Food?",
        "en",
        user_message="find food near me",
        guide_state={"pageKey": "find", "path": "/find"},
    )
    labels = [c["label"] for c in chips]
    assert "Open the form" not in labels
    assert labels[0] == "Open Find Food"  # still show; never "Open the form"
    assert "Do it for me" in labels
    assert "Guide me step by step" in labels


def test_share_fork_keeps_open_the_form():
    from backend.agent.suggestion_chips import share_assistance_fork_chips

    chips = share_assistance_fork_chips(
        "Want me to handle everything in chat, or guide you step by step on Share Food?",
        "en",
        user_message="I want to share food",
    )
    labels = [c["label"] for c in chips]
    assert labels[0] == "Open the form"
    assert "Open Find Food" not in labels


def test_spanish_assist_fork_chips_match_language():
    out = generate_quick_replies(
        "¿Quieres que yo lo haga TODO por ti aquí en el chat, o te guío paso a paso?",
        lang="en",  # sticky lag — chips must still be Spanish
        user_message="Quiero compartir comida",
    )
    assert out == [
        "Abrir el formulario",
        "Hazlo por mí",
        "Guíame paso a paso",
    ]
    assert "Do it for me" not in out


def test_share_assistance_fork_forced_from_reminder():
    from backend.agent.suggestion_chips import share_assistance_fork_chips

    chips = share_assistance_fork_chips(
        "How would you like to proceed?",
        "en",
        user_message="I want to share food",
        assistance_reminder=(
            "ASSISTANCE MODE (required this turn):\n"
            "The user wants to share food. Ask ONCE..."
        ),
    )
    labels = [c["label"] for c in chips]
    assert labels == [
        "Open the form",
        "Do it for me",
        "Guide me step by step",
    ]


def test_share_assistance_fork_from_rephrased_reply():
    from backend.agent.suggestion_chips import share_assistance_fork_chips

    chips = share_assistance_fork_chips(
        "I can help you share — want me to handle it in chat, or prefer "
        "I walk you through the form yourself?",
        "en",
        user_message="share some food",
    )
    labels = [c["label"] for c in chips]
    assert "Open the form" in labels
    assert "Do it for me" in labels
    assert "Guide me step by step" in labels


def test_share_fork_open_form_always_present():
    from backend.agent.suggestion_chips import share_assistance_fork_chips, build_turn_suggestions
    from backend.ai.ai_engine import generate_quick_replies

    t1 = (
        "Great! Would you like me to handle everything for you here in chat, "
        "or would you rather I guide you step by step on the Share Food page?"
    )
    t2 = (
        "Great! Would you like me to handle the whole posting here in chat, "
        "or do you want step-by-step help on the Share Food page? Just pick one below."
    )
    for t in (t1, t2):
        for chips in (
            share_assistance_fork_chips(t, "en", user_message="I want to share food"),
            generate_quick_replies(t, user_message="I want to share food"),
            build_turn_suggestions(
                t, "en", tool_results=[], min_chips=0,
                last_user_message="I want to share food",
            ),
        ):
            labels = [
                c if isinstance(c, str) else c.get("label")
                for c in chips
            ]
            assert labels[0] in ("Open the form", "Abrir el formulario"), labels
            assert "Do it for me" in labels or "Hazlo por mí" in labels
            assert any("step" in (l or "").lower() or "paso" in (l or "").lower() for l in labels)
            assert "5 apples" not in labels


def test_rephrased_share_turns_get_real_chips():
    """Common model rephrasings must not return empty / Yes-No."""
    cases = {
        "Got it. Tell me the food name and roughly how much you have.": ("apple", "bread", "vegetable", "egg"),
        "What should we call this listing?": ("bread", "vegetable", "meal", "fresh"),
        "Please add a short description for recipients.": ("sealed", "homemade", "leftover", "refrigerat"),
        "Where should people pick this up?": ("address", "saved", "different"),
        "Perfect — anything else you want to share today?": ("share", "find", "all"),
        "Your listing is live! Want to share another item?": ("share", "find", "all"),
        "Select Individual/Family or Organization for donor type.": ("individual", "organization"),
        "Cool. Please attach a photo of the food — required before posting.": ("attach", "photo", "adjuntar"),
        "Should I use Alameda Unified for the community?": ("alameda", "different", "profile"),
        "Claim #1 for you — sound good?": ("claim", "cancel", "thanks"),
        "Pick one of the options above (1, 2, or 3).": ("1", "2", "3"),
        "Say yes if you want me to publish now.": ("post", "edit", "cancel"),
        "Ready to post 3 loaves under Alameda Unified, with photo. Shall I post it?": (
            "post", "edit", "cancel",
        ),
    }
    for text, needles in cases.items():
        out = generate_quick_replies(text, user_message="share food")
        assert out, f"empty chips for: {text!r}"
        joined = " ".join(out).lower()
        assert out[:3] != ["Yes", "No", "Later"], text
        assert any(n in joined for n in needles), f"{text!r} -> {out}"
        if "shall i post" in text.lower() or "publish now" in text.lower():
            assert "Attach a photo" not in out, text


def test_do_it_for_me_prechips_match_each_step():
    """Hands-on share chips must match the current question, not a prior step."""
    from backend.agent.suggestion_chips import build_turn_suggestions

    food = generate_quick_replies(
        "You got it! What food do you want to share, and how much do you have?",
        user_message="Do it for me",
    )
    assert "5 apples" in food
    assert "Tomorrow" not in food
    assert "Do it for me" not in food

    qty = generate_quick_replies("How many loaves?", user_message="bread")
    assert "All of them" not in qty
    assert any(s.isdigit() for s in qty)

    community = generate_quick_replies(
        "Should I post this under Alameda Unified School District, "
        "since that is your community?",
        suggested_community="Alameda Unified School District",
        user_message="Do it for me",
    )
    joined = " ".join(community).lower()
    assert "alameda" in joined or "different" in joined
    assert "School District" not in community

    extracted = build_turn_suggestions(
        "Should I post this under Alameda Unified School District, "
        "since that is your community?",
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message="Do it for me",
    )
    labels = [c if isinstance(c, str) else c.get("label") for c in extracted]
    assert "School District" not in labels
    assert any(
        l and ("alameda" in (l or "").lower() or "different" in (l or "").lower())
        for l in labels
    )

    expiry = generate_quick_replies(
        "I'll list this under Alameda Unified. When does it expire?",
        user_message="Do it for me",
    )
    assert "Tomorrow" in expiry
    assert "Still sealed" not in expiry
    assert "Do it for me" not in expiry

    desc = generate_quick_replies(
        "Please add a short description for recipients.",
        user_message="Do it for me",
    )
    assert "Still sealed" in desc
    assert "No allergens" not in desc
    assert "Tomorrow" not in desc
    assert "Attach a photo" not in desc

    photo = generate_quick_replies(
        "Please attach a photo of the food — required before I can post.",
        user_message="Do it for me",
    )
    assert "Attach a photo" in photo
    assert "Still sealed" not in photo
    assert "Yes, post it" not in photo

    confirm = generate_quick_replies(
        "Ready to post 3 loaves under Alameda Unified, with photo. Shall I post it?",
        user_message="Do it for me",
    )
    assert "Yes, post it" in confirm
    assert "Attach a photo" not in confirm
    assert "Tomorrow" not in confirm

    food_open = generate_quick_replies(
        "Perfect. Tell me what you have.",
        user_message="Do it for me",
    )
    assert "5 apples" in food_open or "Bread" in food_open
    assert "Yes, post it" not in food_open
    assert "Attach a photo" not in food_open

    warehouse = generate_quick_replies(
        "List under Do Good Warehouse?",
        suggested_community="Alameda Unified",
        user_message="Do it for me",
    )
    joined_wh = " ".join(warehouse).lower()
    assert "do good warehouse" in joined_wh
    assert "alameda" not in joined_wh
    assert "Different one" in warehouse

    community_post = generate_quick_replies(
        "Want me to post this to your community, Alameda Unified?",
        suggested_community="Alameda Unified",
        user_message="Do it for me",
    )
    assert "Yes, post it" not in community_post
    assert "Attach a photo" not in community_post
    assert "Alameda Unified" in community_post or "Different one" in community_post

    ruby = generate_quick_replies(
        "Your profile is linked to Ruby Bridges Elementary CC. Use that one?",
        user_message="Do it for me",
    )
    joined_ruby = " ".join(ruby).lower()
    assert "ruby bridges" in joined_ruby
    assert "Different one" in ruby
    assert "Attach a photo" not in ruby

    ruby_built = build_turn_suggestions(
        "Your profile is linked to Ruby Bridges Elementary CC. Use that one?",
        "en",
        tool_results=[],
        min_chips=0,
        last_user_message="Do it for me",
    )
    ruby_labels = [c if isinstance(c, str) else c.get("label") for c in ruby_built]
    assert any(l and "ruby bridges" in (l or "").lower() for l in ruby_labels)

    allergen = generate_quick_replies(
        "Does this contain nuts, dairy, eggs, soy, or wheat?",
        user_message="Do it for me",
    )
    assert "No allergens" in allergen
    assert "Still sealed" not in allergen

    look_right = generate_quick_replies(
        "Does this look right? 3 loaves under Alameda Unified, with photo.",
        user_message="Do it for me",
    )
    assert "Yes, post it" in look_right
    assert "Attach a photo" not in look_right
    assert "Yes, claim it" not in look_right

    sound_post = generate_quick_replies(
        "Sound good to post?",
        user_message="Do it for me",
    )
    assert "Yes, post it" in sound_post
    assert "Yes, claim it" not in sound_post
    assert "Attach a photo" not in sound_post

    share_confirm = generate_quick_replies(
        "Shall I go ahead and share this?",
        user_message="Do it for me",
    )
    assert "Yes, post it" in share_confirm
    assert "Attach a photo" not in share_confirm

    desc_alt = generate_quick_replies(
        "Anything else people should know about the food?",
        user_message="Do it for me",
    )
    assert "Still sealed" in desc_alt
    assert "No allergens" not in desc_alt
    assert "Share something else" not in desc_alt

    ready_no_photo = generate_quick_replies(
        "Ready to post: 100 boxes of vegetables under Alameda Unified. "
        "Shall I post these now?",
        user_message="Do it for me",
    )
    assert "Attach a photo" in ready_no_photo
    assert "Yes, post it" not in ready_no_photo

    claim_sound = generate_quick_replies(
        "Claim #1 for you — sound good?",
        user_message="claim it",
    )
    assert "Yes, claim it" in claim_sound
    assert "Yes, post it" not in claim_sound

