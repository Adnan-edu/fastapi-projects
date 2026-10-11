"""Tests for the demo payment gateway."""
import pytest

from app.services.payment import PaymentGateway, PaymentGatewayError


def test_charge_success_returns_receipt():
    receipt = PaymentGateway().charge(user_id=1, amount=19.99)
    assert receipt["user_id"] == 1
    assert receipt["amount"] == 19.99
    assert receipt["status"] == "succeeded"
    assert receipt["transaction_id"]


def test_charge_zero_amount_raises():
    with pytest.raises(PaymentGatewayError):
        PaymentGateway().charge(user_id=1, amount=0)


def test_charge_negative_amount_raises():
    with pytest.raises(PaymentGatewayError):
        PaymentGateway().charge(user_id=1, amount=-5)


def test_charge_over_limit_raises():
    with pytest.raises(PaymentGatewayError):
        PaymentGateway().charge(user_id=1, amount=1_000_000)
