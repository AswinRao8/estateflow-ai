import pytest

from app.utils.response import MAX_RESPONSE_LENGTH, sanitize_response


# ---------------------------------------------------------------------------
# Markdown stripping
# ---------------------------------------------------------------------------

def test_strips_bold():
    assert sanitize_response("This is **important** info") == "This is important info"


def test_strips_italic():
    assert sanitize_response("This is *nice* property") == "This is nice property"


def test_strips_h1_header():
    result = sanitize_response("# Heading\nContent below")
    assert "#" not in result
    assert "Heading" in result


def test_strips_h2_and_h3_headers():
    result = sanitize_response("## Section\n### Subsection\nBody")
    assert "##" not in result
    assert "###" not in result
    assert "Section" in result
    assert "Body" in result


def test_strips_inline_code():
    assert sanitize_response("Use `ref-001` to book") == "Use ref-001 to book"


def test_replaces_hyphen_bullets_with_dot():
    result = sanitize_response("- Three bedrooms\n- Two bathrooms")
    assert "• Three bedrooms" in result
    assert "• Two bathrooms" in result
    assert "- " not in result


def test_replaces_asterisk_bullets_with_dot():
    result = sanitize_response("* Pool\n* Gym")
    assert "• Pool" in result
    assert "* " not in result


def test_strips_leading_and_trailing_whitespace():
    assert sanitize_response("   hello world   ") == "hello world"


def test_plain_text_passes_through_unchanged():
    text = "The villa has 4 bedrooms and is available now."
    assert sanitize_response(text) == text


# ---------------------------------------------------------------------------
# Length enforcement
# ---------------------------------------------------------------------------

def test_short_text_is_not_truncated():
    text = "Short reply."
    result = sanitize_response(text)
    assert result == text
    assert "…" not in result


def test_long_text_is_truncated_to_max_length():
    text = ("word " * 300).strip()
    result = sanitize_response(text)
    assert len(result) <= MAX_RESPONSE_LENGTH + 1  # +1 for the ellipsis character


def test_truncation_appends_ellipsis():
    text = "word " * 300
    result = sanitize_response(text)
    assert result.endswith("…")


def test_truncation_cuts_at_word_boundary():
    # Construct a string where the last word would be cut mid-word at MAX_RESPONSE_LENGTH
    filler = "a" * (MAX_RESPONSE_LENGTH - 5) + " boundary"
    result = sanitize_response(filler)
    assert "boundary" not in result
    assert result.endswith("…")


# ---------------------------------------------------------------------------
# Price hallucination guard
# ---------------------------------------------------------------------------

def test_no_price_check_when_listing_price_is_none():
    text = "This property costs 500000."
    result = sanitize_response(text, listing_price=None)
    assert "500000" in result


def test_matching_price_passes_through():
    result = sanitize_response("Priced at 500000.", listing_price=500000.0)
    assert "500000" in result
    assert "[price on request]" not in result


def test_hallucinated_price_is_replaced():
    result = sanitize_response("This costs 999999.", listing_price=500000.0)
    assert "999999" not in result
    assert "[price on request]" in result


def test_price_within_one_percent_tolerance_passes():
    # 500001 deviates by 0.0002% from 500000 — well within 1%
    result = sanitize_response("Listed at 500001.", listing_price=500000.0)
    assert "500001" in result
    assert "[price on request]" not in result


def test_comma_formatted_price_is_parsed_correctly():
    # "500,000" should be read as 500000
    result = sanitize_response("The price is 500,000.", listing_price=500000.0)
    assert "[price on request]" not in result


def test_comma_formatted_hallucinated_price_is_replaced():
    result = sanitize_response("The price is 999,999.", listing_price=500000.0)
    assert "[price on request]" in result


def test_four_digit_number_is_not_treated_as_price():
    # _PRICE_LIKE requires 5+ digits (d + 4 more = 5 total)
    result = sanitize_response("Unit 1234 is available.", listing_price=500000.0)
    assert "1234" in result
    assert "[price on request]" not in result
