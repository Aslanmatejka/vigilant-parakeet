"""Regression tests for two 'context leaking' bugs in the posting flow.

Both bugs reported by the user after the allergen extractor landed:

  1. Nouri attached the previous listing's photo to a brand-new listing
     that the donor never uploaded a photo for.
  2. Nouri populated ``allergens`` on a listing where the donor never
     declared any — the extractor was over-eagerly bucketing the word
     ``peanuts`` from the assistant's own question ("any peanuts?").

The fix in both cases is scoping: everything before the most recent
'Posted!' / 'Listing #…' success marker belongs to a *previous* listing
and must not bleed into the new one, and the assistant's turns must
never contribute to donor-declared fields.
"""
from __future__ import annotations

from backend.ai.allergens import (
    allergens_answered,
    enrich_post_listing_allergen_args,
)
from backend.ai.conversation_flow import (
    _current_posting_boundary_index,
    _extract_photo_url_for_current_posting,
    _extract_photo_url_from_history,
    enrich_post_food_listing_args,
    posting_flow_state,
)


# ---------------------------------------------------------------------------
# Bug 1: photo from a previously-posted listing must NOT reappear
# ---------------------------------------------------------------------------


class TestPhotoDoesNotLeakAcrossPosts:
    def _history_with_prior_post(self) -> list[dict]:
        return [
            # First listing lifecycle
            {"role": "user", "message": "I want to share bread"},
            {"role": "assistant", "message": "Nice — snap a quick photo?"},
            {"role": "user", "message": "image: /uploads/ai/bread.jpg"},
            {"role": "assistant", "message": "Ready to post?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Posted! Listing #42: 2 loaves of bread."},
            # Second listing starts here — no photo attached this time.
            {"role": "user", "message": "I want to share some cookies too"},
            {"role": "assistant", "message": "Cool — what community?"},
            {"role": "user", "message": "Alameda Unified"},
        ]

    def test_boundary_index_points_after_success(self):
        history = self._history_with_prior_post()
        boundary = _current_posting_boundary_index(history)
        # The 'Posted!' assistant message is at index 5, so the current
        # flow begins at index 6.
        assert boundary == 6

    def test_scoped_photo_lookup_returns_none(self):
        history = self._history_with_prior_post()
        # Even though bread.jpg is in earlier turns, the scoped lookup
        # must return None because it belongs to the completed listing.
        assert _extract_photo_url_for_current_posting(history, "post it") is None

    def test_unscoped_lookup_still_finds_it(self):
        # The unscoped helper (used by 'add a photo to my bread listing')
        # legitimately reaches back and finds the URL. That's the
        # intentional contract of the two functions.
        history = self._history_with_prior_post()
        assert _extract_photo_url_from_history(history, "") == "/uploads/ai/bread.jpg"

    def test_enrich_does_not_reuse_previous_photo(self):
        history = self._history_with_prior_post()
        args = {"title": "cookies", "quantity": 12, "community_name": "Alameda Unified"}
        out = enrich_post_food_listing_args(args, "post it", history)
        # The previous listing's photo must NOT be attached to the new one.
        assert "images" not in out or out["images"] == []

    def test_model_passed_stale_images_are_stripped(self):
        """Model often echoes images[] from full context — must be scrubbed."""
        history = self._history_with_prior_post()
        args = {
            "title": "cookies",
            "quantity": 12,
            "community_name": "Alameda Unified",
            "images": ["/uploads/ai/bread.jpg"],
            "image_url": "/uploads/ai/bread.jpg",
        }
        out = enrich_post_food_listing_args(args, "post it", history)
        assert out.get("images") is None or out.get("images") == []
        assert "image_url" not in out

    def test_done_marker_sets_boundary(self):
        history = [
            {"role": "user", "message": "sharing bread"},
            {"role": "user", "message": "image: /uploads/ai/bread.jpg"},
            {"role": "assistant", "message": "Done! 2 loaves are live under Alameda Unified."},
            {"role": "user", "message": "now sharing rice"},
        ]
        assert _current_posting_boundary_index(history) == 3
        assert _extract_photo_url_for_current_posting(history, "post it") is None

    def test_posting_flow_state_has_photo_scoped(self):
        history = self._history_with_prior_post()
        state = posting_flow_state("post it", history)
        # The photo belonged to the previous listing — the new flow
        # must report has_photo=False so the block-reason keeps asking.
        assert state["has_photo"] is False

    def test_community_confirm_does_not_leak_across_posts(self):
        history = [
            {"role": "user", "message": "share bananas"},
            {"role": "assistant", "message": "List under Alameda Unified?"},
            {"role": "user", "message": "yes"},
            {"role": "assistant", "message": "Posted! Your bananas are live."},
            {"role": "user", "message": "i want to share carrot and tomatoes"},
            {"role": "assistant", "message": "How much do you have?"},
        ]
        state = posting_flow_state("1 basket each", history)
        assert state["community_confirmed"] is False
        assert state["has_photo"] is False

    def test_fresh_photo_within_current_flow_is_kept(self):
        # If the donor uploads a photo AFTER the boundary, it must be
        # picked up normally.
        history = [
            {"role": "assistant", "message": "Posted! Listing #10: apples."},
            {"role": "user", "message": "sharing cookies now"},
            {"role": "assistant", "message": "Snap a photo?"},
            {"role": "user", "message": "image: /uploads/ai/cookies.png"},
        ]
        assert (
            _extract_photo_url_for_current_posting(history, "")
            == "/uploads/ai/cookies.png"
        )

    def test_no_prior_post_scan_full_history(self):
        # First-ever listing (no boundary marker anywhere) — scoped
        # lookup should behave like the unscoped one.
        history = [
            {"role": "user", "message": "sharing bread"},
            {"role": "user", "message": "image: /uploads/ai/bread.jpg"},
        ]
        assert (
            _extract_photo_url_for_current_posting(history, "")
            == "/uploads/ai/bread.jpg"
        )


# ---------------------------------------------------------------------------
# Bug 2: allergens must not leak from assistant text or previous listings
# ---------------------------------------------------------------------------


class TestAllergensDoNotLeakFromAssistantOrPreviousPosts:
    def test_assistant_question_does_not_populate_allergens(self):
        # Before the fix, this was the exact regression: the assistant
        # asked "any peanuts?" and — because donor-frame ingested the
        # full blob — the word 'peanuts' landed in the listing's
        # allergens[]. Now the extractor only reads user text.
        history = [
            {"role": "user", "message": "sharing some cookies"},
            {"role": "assistant", "message": "any peanuts, tree nuts, dairy, or gluten?"},
            {"role": "user", "message": "no, none of those"},
        ]
        args = {"title": "cookies", "quantity": 12}
        out = enrich_post_listing_allergen_args(args, "post it", history)
        assert "allergens" not in out

    def test_donor_negation_does_not_populate_allergens(self):
        # 'no peanuts' is a donor NEGATION — auto framing must route it
        # to exclude_allergens, which we drop on the donor side.
        args = {"title": "cookies"}
        out = enrich_post_listing_allergen_args(
            args, "no peanuts, made from scratch", history=[],
        )
        assert "allergens" not in out

    def test_donor_bare_food_word_is_not_an_allergen_declaration(self):
        # 'sharing peanut butter cookies' is a title — no explicit
        # 'contains' framing, so we shouldn't auto-populate allergens.
        # The AI can still add them via the explicit policy.
        args = {"title": "peanut butter cookies"}
        out = enrich_post_listing_allergen_args(
            args, "sharing peanut butter cookies", history=[],
        )
        assert "allergens" not in out

    def test_explicit_donor_contains_still_populates(self):
        # The safety-net path must still work: 'these contain peanuts'
        # by the donor must add peanuts to allergens.
        args = {"title": "cookies"}
        out = enrich_post_listing_allergen_args(
            args, "these contain peanuts and dairy", history=[],
        )
        assert "peanuts" in out.get("allergens", [])
        assert "milk" in out.get("allergens", [])

    def test_previous_listing_allergens_do_not_bleed(self):
        # First listing declared peanuts. Second listing (post the
        # 'Posted!' boundary) never mentions any. Nothing should leak.
        history = [
            {"role": "user", "message": "sharing cookies that contain peanuts"},
            {"role": "assistant", "message": "Posted! Listing #7: cookies with peanuts."},
            {"role": "user", "message": "now sharing apples"},
        ]
        args = {"title": "apples", "quantity": 6}
        out = enrich_post_listing_allergen_args(args, "post it", history)
        assert "allergens" not in out

    def test_allergens_answered_ignores_assistant_question(self):
        # Before the fix, an assistant question containing the word
        # 'allergens' incorrectly counted as 'answered' via keyword
        # match. Now only donor utterances count.
        history = [
            {"role": "assistant", "message": "Any allergens I should know about?"},
        ]
        assert allergens_answered("", history) is False

    def test_allergens_answered_by_donor_none(self):
        # A donor "no allergens" reply DOES count as answered.
        history = [
            {"role": "assistant", "message": "Any allergens I should know about?"},
        ]
        assert allergens_answered("no allergens", history) is True

    def test_allergens_answered_scoped_to_current_flow(self):
        # A donor allergen declaration from a previous listing must
        # NOT satisfy the answer for the current flow.
        history = [
            {"role": "user", "message": "sharing cookies that contain peanuts"},
            {"role": "assistant", "message": "Posted! Listing #7: cookies."},
            {"role": "user", "message": "now sharing new muffins"},
        ]
        assert allergens_answered("post it", history) is False
