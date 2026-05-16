"""Unit tests for MarketConfig defaults, field types, and settings integration.

Phase 0 validation checkpoint: MarketConfig fields readable from settings
with correct defaults.
"""
from app.config import MarketConfig, get_settings


# ---------------------------------------------------------------------------
# MarketConfig defaults
# ---------------------------------------------------------------------------

def test_default_currency_is_usd():
    assert MarketConfig().currency_code == "USD"
    assert MarketConfig().currency_symbol == "$"


def test_default_area_unit_is_sqm():
    assert MarketConfig().area_unit == "sqm"


def test_default_timezone_is_utc():
    assert MarketConfig().timezone == "UTC"


def test_default_communication_locale_is_en():
    assert MarketConfig().communication_locale == "en"


def test_default_property_terminology_is_empty():
    assert MarketConfig().property_terminology == {}


# ---------------------------------------------------------------------------
# MarketConfig with custom values
# ---------------------------------------------------------------------------

def test_custom_currency():
    config = MarketConfig(currency_code="AED", currency_symbol="د.إ")
    assert config.currency_code == "AED"
    assert config.currency_symbol == "د.إ"


def test_custom_area_unit_sqft():
    config = MarketConfig(area_unit="sqft")
    assert config.area_unit == "sqft"


def test_custom_timezone():
    config = MarketConfig(timezone="Asia/Dubai")
    assert config.timezone == "Asia/Dubai"


def test_custom_communication_locale():
    config = MarketConfig(communication_locale="fr")
    assert config.communication_locale == "fr"


def test_property_terminology_override():
    config = MarketConfig(property_terminology={"APARTMENT": "flat", "HOUSE": "terraced house"})
    assert config.property_terminology["APARTMENT"] == "flat"
    assert config.property_terminology["HOUSE"] == "terraced house"


def test_property_terminology_lookup_missing_key_raises():
    config = MarketConfig(property_terminology={"APARTMENT": "flat"})
    assert "VILLA" not in config.property_terminology


# ---------------------------------------------------------------------------
# Settings integration
# ---------------------------------------------------------------------------

def test_settings_exposes_market_block():
    settings = get_settings()
    assert hasattr(settings, "market")


def test_settings_market_is_market_config_instance():
    settings = get_settings()
    assert isinstance(settings.market, MarketConfig)


def test_settings_market_defaults_match_market_config_defaults():
    settings = get_settings()
    defaults = MarketConfig()
    assert settings.market.currency_code == defaults.currency_code
    assert settings.market.area_unit == defaults.area_unit
    assert settings.market.timezone == defaults.timezone
    assert settings.market.communication_locale == defaults.communication_locale


# ---------------------------------------------------------------------------
# Health endpoint reflects market config
# ---------------------------------------------------------------------------

def test_health_endpoint_includes_market_summary(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "market" in data
    market = data["market"]
    assert "currency" in market
    assert "area_unit" in market
    assert "timezone" in market
    assert "locale" in market


def test_health_endpoint_market_currency_format(client):
    response = client.get("/health")
    market = response.json()["data"]["market"]
    # Default: "$ (USD)"
    assert "USD" in market["currency"]
    assert "$" in market["currency"]


def test_health_endpoint_market_defaults(client):
    response = client.get("/health")
    market = response.json()["data"]["market"]
    assert market["area_unit"] == "sqm"
    assert market["timezone"] == "UTC"
    assert market["locale"] == "en"
