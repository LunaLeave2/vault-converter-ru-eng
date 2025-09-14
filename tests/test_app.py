from decimal import Decimal
import pytest
import converter.core as coremod
from converter.core import ConverterCore, parse_pair


def test_parse_pair_variants():
    assert parse_pair("usd-eur") == ("USD", "EUR")
    assert parse_pair("USD - EUR") == ("USD", "EUR")
    assert parse_pair("usd eur") == ("USD", "EUR")
    assert parse_pair("usd/eur") == ("USD", "EUR")
    assert parse_pair("usd to eur") == ("USD", "EUR")
    assert parse_pair("usd в eur") == ("USD", "EUR")


def test_convert_math_with_fake_rates(tmp_path, monkeypatch):
    def fake_fetch_usd_rates():
        # Формат: USD->X
        return (
            {
                "USD": Decimal("1"),
                "EUR": Decimal("0.90"),
                "RUB": Decimal("90"),
                "BTC": Decimal("0.000025"),  # 1 USD = 0.000025 BTC  =>  1 BTC = 40 000 USD
            },
            "fake",
        )

    monkeypatch.setattr(coremod, "fetch_usd_rates", fake_fetch_usd_rates)

    db = tmp_path / "rates.sqlite3"
    core = ConverterCore(db_path=db)

    # USD -> EUR
    res = core.convert("USD", "EUR", Decimal("10"))
    assert res.rate == Decimal("0.90")
    assert res.result == Decimal("9.00")

    # EUR -> USD
    res2 = core.convert("EUR", "USD", Decimal("9"))
    assert res2.rate.quantize(Decimal("0.0001")) == Decimal("1.1111")

    # BTC -> EUR
    res3 = core.convert("BTC", "EUR", Decimal("1"))
    assert res3.rate == Decimal("36000")


def test_forced_update_when_symbol_missing(tmp_path, monkeypatch):


    calls = {"n": 0}

    def fetch_step():
        calls["n"] += 1
        # 1-й вызов (инициализация БД): без USDC
        if calls["n"] == 1:
            return (
                {"USD": Decimal("1"), "EUR": Decimal("0.9")},  # USDC ещё нет
                "fake-1",
            )
        # 2-й вызов (force update): USDC уже есть
        return (
            {"USD": Decimal("1"), "EUR": Decimal("0.9"), "USDC": Decimal("1")},
            "fake-2",
        )

    monkeypatch.setattr(coremod, "fetch_usd_rates", fetch_step)

    db = tmp_path / "rates.sqlite3"
    core = ConverterCore(db_path=db)

    res = core.convert("USD", "USDC", Decimal("5"))
    assert res.rate == Decimal("1")
    assert res.result == Decimal("5.00")
