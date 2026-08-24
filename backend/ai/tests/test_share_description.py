"""Do-it-for-me must ask for a donor-written description and save it."""
from __future__ import annotations

from backend.ai.ai_engine import generate_quick_replies
from backend.ai.conversation_flow import (
    _best_user_description_from_thread,
    _is_description_ask,
    build_posting_step_reminder,
    enrich_post_food_listing_args,
    posting_flow_state,
    posting_tool_block_reason,
)


def _share_through_expiry():
    return [
        {"role": "user", "message": "I want to share leftover lasagna"},
        {"role": "assistant", "message": "Should this go under Do Good Warehouse?"},
        {"role": "user", "message": "yes"},
        {"role": "assistant", "message": "When does it expire?"},
        {"role": "user", "message": "tomorrow"},
    ]


class TestDescriptionAskDetection:
    def test_short_description_prompt_is_an_ask(self):
        assert _is_description_ask(
            "Please add a short description for recipients."
        )
        assert _is_description_ask(
            "Got it. One sentence about the food — condition or packaging?"
        )
        assert _is_description_ask(
            "Tell me a bit about the food so people know what they're getting."
        )

    def test_mentioning_description_field_is_not_an_ask(self):
        assert not _is_description_ask(
            "I'll put pickup only in the description. Please attach a photo."
        )


class TestMustAskAfterExpiry:
    def test_leftover_share_is_not_already_a_description(self):
        history = _share_through_expiry()[:-1]
        state = posting_flow_state("tomorrow", history)
        assert state["expiry_provided"] is True
        assert state["description_provided"] is False
        assert state["description_asked"] is False

    def test_reminder_after_expiry_asks_for_description(self):
        history = _share_through_expiry()[:-1]
        reminder = build_posting_step_reminder("tomorrow", history, lang="en")
        assert reminder is not None
        low = reminder.lower()
        assert "description" in low
        assert "do not invent" in low or "their words" in low
        assert "do not ask again" in low or "already gave" in low

    def test_waiting_after_description_question(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
        ]
        reminder = build_posting_step_reminder("ok", history, lang="en")
        assert reminder is not None
        assert "description" in reminder.lower()
        assert "wait" in reminder.lower() or "do not invent" in reminder.lower()

    def test_post_blocked_until_donor_describes(self):
        history = _share_through_expiry()
        reason = posting_tool_block_reason(
            "yes post it",
            history,
            {
                "title": "lasagna",
                "qty": 1,
                "community_name": "Do Good Warehouse",
                "community_confirmed": True,
                "expiration_date": "2030-07-10",
                "images": ["https://cdn.example.com/lasagna.jpg"],
            },
        )
        assert reason is not None
        assert "description" in reason.lower()


class TestDescriptionSavedOnPost:
    def test_chip_answer_is_stored(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
        ]
        assert (
            _best_user_description_from_thread("Fresh today", history)
            == "Fresh today"
        )
        state = posting_flow_state("Fresh today", history)
        assert state["description_asked"] is True
        assert state["description_provided"] is True
        out = enrich_post_food_listing_args(
            {"title": "lasagna", "qty": 1},
            "Fresh today",
            history,
        )
        assert out.get("description") == "Fresh today"

    def test_typed_sentence_is_stored(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
            {
                "role": "user",
                "message": "Homemade, still in the pan, refrigerated.",
            },
        ]
        out = enrich_post_food_listing_args(
            {"title": "lasagna", "description": "Pickup only."},
            "yes post it",
            history,
        )
        assert "Homemade" in (out.get("description") or "")
        assert "Pickup only" not in (out.get("description") or "")

    def test_fresh_today_chip_does_not_overwrite_expiry(self):
        history = _share_through_expiry() + [
            {
                "role": "assistant",
                "message": "Please add a short description for recipients.",
            },
        ]
        out = enrich_post_food_listing_args(
            {"title": "lasagna"},
            "Fresh today",
            history,
        )
        assert out.get("description") == "Fresh today"
        exp = out.get("expiration_date") or out.get("expiry_date")
        assert exp
        # Expiry came from "tomorrow", not from the description chip.
        from datetime import date, timedelta
        assert exp == (date.today() + timedelta(days=1)).isoformat()


class TestDescriptionChips:
    def test_description_ask_gets_description_chips(self):
        out = generate_quick_replies(
            "Please add a short description for recipients.",
            user_message="share leftover lasagna",
        )
        joined = " ".join(out).lower()
        assert "sealed" in joined or "homemade" in joined or "leftover" in joined
        assert "fresh today" not in joined
        assert "no allergens" not in joined
        assert out[:3] != ["Yes", "No", "Later"]
        assert "Attach a photo" not in out
        assert "Tomorrow" not in out

    def test_tell_me_a_bit_more_gets_description_chips(self):
        out = generate_quick_replies(
            "Can you tell me a bit more about the food so people know "
            "what they are getting?",
            user_message="Do it for me",
        )
        joined = " ".join(out).lower()
        assert "sealed" in joined or "homemade" in joined
        assert "Tomorrow" not in out
        assert "Do it for me" not in out

    def test_common_description_rephrases_get_matching_chips(self):
        phrases = [
            "What should I put as the description?",
            "Listing description?",
            "Description?",
            "Got it — expires tomorrow. What's a short description I can put on the listing?",
            "How is it packaged / what's included?",
            "Help me with a listing description — one sentence is enough.",
            "Give me a sentence about the food.",
            "I need a short blurb about the food.",
            "What should the listing say about this food?",
            "Anything I should mention on the listing?",
            "One sentence for the post?",
            "A sentence for the description field?",
        ]
        for text in phrases:
            assert _is_description_ask(text), text
            out = generate_quick_replies(text, user_message="Do it for me")
            assert out, f"empty chips for: {text!r}"
            joined = " ".join(out).lower()
            assert any(n in joined for n in ("sealed", "homemade", "leftover")), (
                f"{text!r} -> {out}"
            )
            assert "Attach a photo" not in out, text
            assert "Tomorrow" not in out, text
            assert "Yes, post it" not in out, text
            assert "No allergens" not in out, text

    def test_narrating_description_field_still_not_an_ask(self):
        assert not _is_description_ask(
            "I'll put pickup only in the description. Please attach a photo."
        )
        out = generate_quick_replies(
            "I'll put pickup only in the description. Please attach a photo "
            "— required before I can post.",
            user_message="Do it for me",
        )
        assert "Attach a photo" in out
        assert "Still sealed" not in out

    def test_expiry_ack_plus_describing_ask_gets_description_chips(self):
        text = (
            "Got it, I'll mark the bread as good for 3 more days. "
            "Can you write one short sentence describing the bread "
            "(like what kind, how it's packed, or anything special)?"
        )
        assert _is_description_ask(text)
        from backend.ai.ai_engine import _is_expiry_ask
        assert not _is_expiry_ask(text.lower())
        out = generate_quick_replies(text, user_message="Do it for me")
        assert "Still sealed" in out or "Homemade, refrigerated" in out
        assert "Tomorrow" not in out
        assert "In 2 days" not in out
        assert "Attach a photo" not in out

    def test_description_does_not_fire_on_higher_priority_turns(self):
        """Post-confirm, claim, community, photo, and success turns keep their
        chips even when the assistant's copy mentions 'description'."""
        cases = [
            # Post-confirm summary that recaps a saved description.
            (
                "Great — 2 loaves, description saved, with photo. Ready to post?",
                "Yes, post it",
            ),
            # Community ask that mentions "your description will be on the listing".
            (
                "Which community should I list this under? I'll include your "
                "description on the listing.",
                None,  # community chips
            ),
            # Claim confirm with "anything special".
            (
                "Claim #1 for you — sound good? Anything special I should note?",
                "Yes, claim it",
            ),
            # Photo required with "how it's packed" narration.
            (
                "Take a clear photo showing how it's packed — required before I "
                "can post.",
                "Attach a photo",
            ),
            # Food search "what kind of food" must not become a description ask.
            (
                "What kind of food are you looking for?",
                "Bread",
            ),
        ]
        for text, expected in cases:
            out = generate_quick_replies(text, user_message="Do it for me")
            assert "Still sealed" not in out, f"description chip leaked into: {text!r} -> {out}"
            if expected:
                assert any(expected in c for c in out), (
                    f"{text!r} -> {out}, expected {expected!r}"
                )


class TestDoItForMeFullFlowChips:
    """End-to-end regression coverage: every step of the DoFM share flow."""

    def _chips(self, text: str, *, um: str = "Do it for me", suggested: str | None = None):
        return generate_quick_replies(
            text, user_message=um, suggested_community=suggested,
        )

    def test_step_food_and_amount(self):
        for text in [
            "You got it! What food do you want to share, and how much do you have?",
            "Perfect. Tell me what you have.",
            "Got it. Tell me the food name and roughly how much you have.",
            "What food and how much would you like to share?",
        ]:
            out = self._chips(text)
            assert any("apples" in c for c in out), f"{text!r} -> {out}"
            for bad in ("Tomorrow", "Attach a photo", "Yes, post it", "Still sealed"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_bare_quantity(self):
        for text in ["How many loaves?", "How many pieces are you sharing?"]:
            out = self._chips(text)
            assert "1" in out and "3" in out and "5" in out
            for bad in ("Yes, post it", "Attach a photo", "Still sealed", "Tomorrow"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_community_named(self):
        cases = [
            ("List under Do Good Warehouse?", "Do Good Warehouse", "Alameda Unified"),
            (
                "Want me to post this to your community, Alameda Unified?",
                "Alameda Unified",
                "Alameda Unified",
            ),
            (
                "Your profile is linked to Ruby Bridges Elementary CC. Use that one?",
                "Ruby Bridges",
                None,
            ),
        ]
        for text, expected_name, suggested in cases:
            out = self._chips(text, suggested=suggested)
            assert any(expected_name in c for c in out), (
                f"{text!r} -> {out}, wanted {expected_name!r}"
            )
            assert "Different one" in out, f"{text!r} -> {out}"
            for bad in ("Yes, post it", "Attach a photo", "Tomorrow", "Still sealed"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_expiry(self):
        for text in [
            "When does it expire?",
            "How long is this good for?",
            "Best-by or use-by date?",
            "Got it. What's the best-by date?",
            "I'll list this under Alameda Unified. When does it expire?",
        ]:
            out = self._chips(text)
            assert "Tomorrow" in out and "In 2 days" in out, f"{text!r} -> {out}"
            for bad in ("Yes, post it", "Attach a photo", "Still sealed", "No allergens"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_description(self):
        for text in [
            "Please add a short description for recipients.",
            "Can you write one short sentence describing the bread?",
            "Anything else people should know about the food?",
            "Describe the food in one sentence.",
            "Listing description?",
            "Description?",
            "One-sentence description of the food?",
            "What should I put as the description?",
            "How would you describe it for recipients?",
        ]:
            out = self._chips(text)
            assert any("sealed" in c.lower() or "homemade" in c.lower() for c in out), (
                f"{text!r} -> {out}"
            )
            for bad in ("Tomorrow", "In 2 days", "Yes, post it", "Attach a photo", "No allergens"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_photo(self):
        for text in [
            "Please attach a photo of the food — required before I can post.",
            "Now upload a photo — required before posting.",
            "Add a photo — I can't post without one.",
        ]:
            out = self._chips(text)
            assert "Attach a photo" in out, f"{text!r} -> {out}"
            for bad in ("Yes, post it", "Still sealed", "Tomorrow"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_final_confirm_with_photo(self):
        for text in [
            "Ready to post 3 loaves under Alameda Unified, with photo. Shall I post it?",
            "Does this look right? 3 loaves under Alameda Unified, with photo.",
            "Sound good to post?",
            "Shall I go ahead and share this?",
            "Ready to post: 2 loaves under Do Good Warehouse, with photo. Shall I post these now?",
        ]:
            out = self._chips(text)
            assert "Yes, post it" in out, f"{text!r} -> {out}"
            for bad in ("Attach a photo", "Tomorrow", "Still sealed", "Yes, claim it"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_final_confirm_without_photo_prompts_photo(self):
        for text in [
            "Thanks for that! You've got 2 loaves of bread and 1 freshly made piece, "
            "both good until August 30, at Do Good Warehouse with pickup at your place. "
            "Ready to post these?",
            "Ready to post: 100 boxes of vegetables under Alameda Unified. Shall I post these now?",
        ]:
            out = self._chips(text)
            assert "Attach a photo" in out, f"{text!r} -> {out}"
            for bad in ("Yes, post it", "Tomorrow", "Still sealed"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_success(self):
        for text in [
            "Posted! Listing #42 is live. Share another item?",
            "Your listing is live! Want to share another?",
        ]:
            out = self._chips(text)
            assert any("Share" in c or "Find" in c for c in out), f"{text!r} -> {out}"
            for bad in ("Yes, post it", "Attach a photo", "Tomorrow", "Still sealed"):
                assert bad not in out, f"{bad} leaked into {text!r} -> {out}"

    def test_step_allergens(self):
        out = self._chips("Does this contain nuts, dairy, eggs, soy, or wheat?")
        assert "No allergens" in out
        for bad in ("Tomorrow", "Still sealed", "Yes, post it"):
            assert bad not in out, f"{bad} leaked into out={out}"

    def test_step_claim_confirm_not_post_confirm(self):
        out = self._chips("Claim #1 for you — sound good?", um="claim it")
        assert "Yes, claim it" in out
        for bad in ("Yes, post it", "Attach a photo", "Still sealed"):
            assert bad not in out, f"{bad} leaked into out={out}"

    def test_step_pickup_window_after_expiry_ack(self):
        out = self._chips("Got it — good until tomorrow. When can people pick it up?")
        assert any("Today" in c or "Tomorrow morning" in c for c in out), out
        for bad in ("Still sealed", "In 2 days"):
            assert bad not in out, f"{bad} leaked into out={out}"

    def test_no_duplicate_labels_across_flow(self):
        """No chip label should repeat within a single reply's chip set."""
        replies = [
            "You got it! What food do you want to share, and how much do you have?",
            "How many loaves?",
            "List under Do Good Warehouse?",
            "When does it expire?",
            "Please add a short description for recipients.",
            "Please attach a photo of the food — required before I can post.",
            "Ready to post 3 loaves under Alameda Unified, with photo. Shall I post it?",
            "Posted! Listing #42 is live. Share another item?",
        ]
        for r in replies:
            out = self._chips(r)
            dupes = [c for c in out if out.count(c) > 1]
            assert not dupes, f"duplicates {dupes} in {r!r} -> {out}"

    def test_chips_are_idempotent(self):
        text = "Please add a short description for recipients."
        first = self._chips(text)
        second = self._chips(text)
        assert first == second

    # ── Regression: prod transcripts (2026-08-25) where "no allergens" in
    # an ack / summary triggered allergen chips on unrelated turns.
    def test_ack_no_allergens_then_description_ask(self):
        text = (
            "Perfect, no allergens. Please write one short sentence "
            "describing the veggies—like what's inside or how they're packed."
        )
        out = self._chips(text)
        assert "Still sealed" in out, out
        assert "No allergens" not in out, out

    def test_post_confirm_recap_with_no_allergens(self):
        text = (
            "Photo received! Here's your post: 1 box of assorted leftover "
            "vegetables (not packed), no allergens, under Alameda Unified "
            "School District, pickup at 1423 Park St, good for about a month. "
            "Ready to post?"
        )
        out = self._chips(text)
        assert "Yes, post it" in out, out
        for bad in ("No allergens", "Attach a photo", "Tomorrow", "Still sealed"):
            assert bad not in out, f"{bad} leaked into {out}"

    def test_description_ask_after_expiry_ack_with_no_allergens_context(self):
        text = (
            "Got it — your food is good for another month. Could you tell me "
            "one short sentence describing the food? For example, what's "
            "included, its condition, or how it's packaged?"
        )
        out = self._chips(text)
        assert "Still sealed" in out, out
        for bad in ("No allergens", "Tomorrow", "In 2 days", "Yes, post it"):
            assert bad not in out, f"{bad} leaked into {out}"

    def test_post_confirm_recap_with_photo_and_no_allergens(self):
        text = (
            "Perfect, thanks for the photo! Here's what I have: 5 apples "
            "(not sealed), no allergens, good for another month, pickup at "
            "1423 Park St, for Do Good Warehouse. Ready to post this?"
        )
        out = self._chips(text)
        assert "Yes, post it" in out, out
        for bad in ("No allergens", "Attach a photo", "Tomorrow", "Still sealed"):
            assert bad not in out, f"{bad} leaked into {out}"

    def test_food_description_ask_after_allergen_ack(self):
        text = (
            "Great, thanks for letting me know! Please tell me in one "
            "sentence what you're sharing — like what it is, how many, and "
            "how it's packaged."
        )
        out = self._chips(text)
        assert any("apples" in c for c in out), out
        for bad in ("No allergens", "Still sealed", "Tomorrow", "Yes, post it"):
            assert bad not in out, f"{bad} leaked into {out}"

    def test_actual_allergen_ask_still_fires(self):
        text = (
            "Perfect, thank you! Are there any allergens in the food, like "
            "peanuts, tree nuts, dairy, eggs, wheat/gluten, soy, fish, "
            "shellfish, or sesame? If not, just say none."
        )
        out = self._chips(text)
        assert "No allergens" in out, out
        for bad in ("Still sealed", "Yes, post it", "Attach a photo"):
            assert bad not in out, f"{bad} leaked into {out}"
