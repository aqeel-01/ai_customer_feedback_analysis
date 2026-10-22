"""
unit/test_filter.py
===================
Tests for feedback_analyzer.filtering.filter.is_qualifying().

Covers:
  - Core customer feedback scenarios
  - Single-word greetings
  - Multi-word social pleasantries
  - Spam / promotional broadcasts (keyword patterns + heuristic)
  - Legitimate requests (bug, feature, billing, general inquiry)
  - Greeting-prefixed legitimate requests (must qualify)
  - Edge cases (very short messages, punctuation-only)
"""

from __future__ import annotations

from feedback_analyzer.filtering.filter import is_qualifying
from feedback_analyzer.schemas.input_schema import RawTicket


def _ticket(message: str, tid: str = "TX") -> RawTicket:
    """Helper: create a RawTicket with minimal required fields."""
    return RawTicket(ticket_id=tid, message=message)


# ---------------------------------------------------------------------------
# Core customer feedback scenarios
# ---------------------------------------------------------------------------


class TestCoreFeedbackScenarios:
    def test_scenario_1_bug_report_qualifies(self):
        """Scenario 1: payment page crash → must qualify (Bug Report, Urgent, Negative)."""
        qualifying, reason = is_qualifying(
            _ticket(
                "The payment page crashes every time I click 'Checkout' on Chrome."
                " Please fix this ASAP!"
            )
        )
        assert qualifying is True
        assert reason == ""

    def test_scenario_2_feature_request_qualifies(self):
        """Scenario 2: dark-mode request starting with 'Hi team' → must qualify."""
        qualifying, reason = is_qualifying(
            _ticket(
                "Hi team, it would be awesome if you could add a dark mode"
                " to the mobile app."
            )
        )
        assert qualifying is True
        assert reason == ""

    def test_scenario_3_greeting_pleasantry_ignored(self):
        """Scenario 3: pure social greeting → must be IGNORED."""
        qualifying, reason = is_qualifying(
            _ticket("Hello, hope you are having a nice day!")
        )
        assert qualifying is False
        assert reason != ""


# ---------------------------------------------------------------------------
# Greeting and social pleasantry detection
# ---------------------------------------------------------------------------


class TestGreetings:
    def test_single_word_hi_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Hi"))
        assert qualifying is False

    def test_single_word_hello_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Hello"))
        assert qualifying is False

    def test_single_word_hey_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Hey"))
        assert qualifying is False

    def test_single_word_howdy_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Howdy"))
        assert qualifying is False

    def test_hi_with_exclamation_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Hi!"))
        assert qualifying is False

    def test_hello_with_exclamation_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Hello!"))
        assert qualifying is False

    def test_good_morning_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Good morning"))
        assert qualifying is False

    def test_good_morning_with_punctuation_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Good morning!"))
        assert qualifying is False

    def test_hello_there_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Hello there"))
        assert qualifying is False

    def test_hey_team_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Hey team"))
        assert qualifying is False

    def test_ignore_reason_mentions_greeting(self):
        _, reason = is_qualifying(_ticket("Hi"))
        assert "greeting" in reason.lower() or "pleasantry" in reason.lower()


# ---------------------------------------------------------------------------
# Spam and promotional broadcasts
# ---------------------------------------------------------------------------


class TestSpamAndPromotional:
    def test_buy_now_pattern_ignored(self):
        qualifying, reason = is_qualifying(
            _ticket("BUY NOW!!! LIMITED OFFER — 90% OFF ALL PRODUCTS TODAY ONLY!!!")
        )
        assert qualifying is False
        assert "spam" in reason.lower() or "promotional" in reason.lower()

    def test_percentage_off_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Get 50% off today only! Shop now!"))
        assert qualifying is False

    def test_limited_offer_keyword_ignored(self):
        qualifying, _ = is_qualifying(
            _ticket("Limited offer: click here to claim your free gift.")
        )
        assert qualifying is False

    def test_flash_sale_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Flash sale ends tonight — order now!"))
        assert qualifying is False

    def test_all_caps_many_exclamations_ignored(self):
        qualifying, _ = is_qualifying(
            _ticket("FLASH SALE!!! DON'T MISS OUT!!! ORDER NOW!!!")
        )
        assert qualifying is False

    def test_act_now_keyword_ignored(self):
        qualifying, _ = is_qualifying(_ticket("Act now and get 30% off your purchase."))
        assert qualifying is False

    def test_unsubscribe_keyword_ignored(self):
        qualifying, _ = is_qualifying(
            _ticket("Click here to unsubscribe from our mailing list.")
        )
        assert qualifying is False


# ---------------------------------------------------------------------------
# Legitimate customer requests — must qualify
# ---------------------------------------------------------------------------


class TestQualifyingMessages:
    def test_billing_duplicate_charge_qualifies(self):
        qualifying, reason = is_qualifying(
            _ticket(
                "I was charged twice for my subscription this month."
                " Please refund the duplicate charge."
            )
        )
        assert qualifying is True
        assert reason == ""

    def test_general_inquiry_export_qualifies(self):
        qualifying, _ = is_qualifying(
            _ticket("How do I export my data to CSV from the dashboard?")
        )
        assert qualifying is True

    def test_bug_report_firefox_qualifies(self):
        qualifying, _ = is_qualifying(
            _ticket(
                "The search feature is completely broken on Firefox —"
                " results don't load at all."
            )
        )
        assert qualifying is True

    def test_greeting_prefixed_login_issue_qualifies(self):
        """A message beginning with 'Hello!' but containing a real issue must qualify."""
        qualifying, _ = is_qualifying(
            _ticket(
                "Hello! I've been having issues logging into my account for two days now."
            )
        )
        assert qualifying is True

    def test_greeting_prefixed_billing_issue_qualifies(self):
        qualifying, _ = is_qualifying(
            _ticket("Hi, I was overcharged on my last invoice. Can you help?")
        )
        assert qualifying is True

    def test_short_but_actionable_message_qualifies(self):
        qualifying, _ = is_qualifying(_ticket("App is broken."))
        assert qualifying is True

    def test_feature_request_no_greeting_qualifies(self):
        qualifying, _ = is_qualifying(
            _ticket("Please add multi-language support to the settings page.")
        )
        assert qualifying is True
