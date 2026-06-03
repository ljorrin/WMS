"""Tests GS1 (FR-011/056) — puro cálculo, sin BD."""
from app.core.gs1 import gs1_check_digit, is_valid_gtin, generate_sscc


def test_check_digit_conocido():
    # GTIN-13 0012345678905 → dígito de control 5
    assert gs1_check_digit("001234567890") == 5
    assert is_valid_gtin("0012345678905")


def test_gtin_invalido():
    assert not is_valid_gtin("0012345678901")
    assert not is_valid_gtin("abc")
    assert not is_valid_gtin("123")


def test_sscc_18_digitos_y_valido():
    s = generate_sscc("1234567", serial=42)
    assert len(s) == 18 and s.isdigit()
    # el último dígito es el control del resto
    assert gs1_check_digit(s[:-1]) == int(s[-1])

def test_sscc_unico():
    a = generate_sscc("1234567"); b = generate_sscc("1234567")
    assert len(a) == 18 and len(b) == 18
