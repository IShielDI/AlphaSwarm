"""Unit tests for operator CLI status script (scripts/operator_status.py)."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from scripts.operator_status import get_status_payload, format_currency, format_pct, str_enum


def test_format_helpers():
    assert format_currency(1234.56) == "$1,234.56"
    assert format_currency(None) == "N/A"
    assert format_pct(0.0525) == "+5.25%"
    assert format_pct(-0.021) == "-2.10%"
    assert str_enum("AccountStatus.ACTIVE") == "ACTIVE"


def test_get_status_payload():
    mock_client = MagicMock()
    mock_account = MagicMock()
    mock_account.account_number = "PA12345"
    mock_account.status = "ACTIVE"
    mock_account.equity = "100000.00"
    mock_account.cash = "50000.00"
    mock_account.buying_power = "200000.00"
    mock_account.daytrading_buying_power = None
    mock_account.portfolio_value = "100000.00"
    mock_account.pattern_day_trader = False
    mock_account.trading_blocked = False
    mock_account.transfers_blocked = False
    mock_account.account_blocked = False

    mock_position = MagicMock()
    mock_position.symbol = "AAPL"
    mock_position.qty = "10"
    mock_position.side = "long"
    mock_position.market_value = "1500.00"
    mock_position.avg_entry_price = "140.00"
    mock_position.current_price = "150.00"
    mock_position.unrealized_pl = "100.00"
    mock_position.unrealized_plpc = "0.0714"
    mock_position.asset_class = "us_equity"

    mock_order = MagicMock()
    mock_order.id = "ord-123"
    mock_order.symbol = "AAPL"
    mock_order.side = "buy"
    mock_order.qty = "5"
    mock_order.type = "limit"
    mock_order.status = "new"
    mock_order.limit_price = "145.00"
    mock_order.submitted_at = "2026-08-29T12:00:00Z"

    mock_client.get_account.return_value = mock_account
    mock_client.get_positions.return_value = [mock_position]
    mock_client.get_orders.return_value = [mock_order]

    payload = get_status_payload(mock_client)

    assert payload["account"]["account_number"] == "PA12345"
    assert payload["account"]["equity"] == 100000.0
    assert len(payload["positions"]) == 1
    assert payload["positions"][0]["symbol"] == "AAPL"
    assert len(payload["open_orders"]) == 1
    assert payload["open_orders"][0]["id"] == "ord-123"
