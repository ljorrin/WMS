"""
WMS Panamá — Utilidades GS1 (FR-011 / FR-056)
==============================================
Dígito de control GS1 (mod-10) para GTIN-8/12/13/14 y SSCC, validación de
GTIN y generación de SSCC (Serial Shipping Container Code, 18 dígitos).

Puro cálculo — sin dependencias externas.
"""

from __future__ import annotations

import time


def gs1_check_digit(payload: str) -> int:
    """Calcula el dígito de control GS1 (mod-10) sobre los dígitos `payload`
    (sin incluir el dígito de control). Aplica pesos 3 y 1 de derecha a izquierda.
    """
    if not payload or not payload.isdigit():
        raise ValueError("El payload GS1 debe ser numérico.")
    total = 0
    for i, ch in enumerate(reversed(payload)):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    return (10 - (total % 10)) % 10


def is_valid_gtin(gtin: str) -> bool:
    """Valida un GTIN-8/12/13/14 verificando su dígito de control."""
    if not gtin or not gtin.isdigit() or len(gtin) not in (8, 12, 13, 14):
        return False
    return gs1_check_digit(gtin[:-1]) == int(gtin[-1])


def generate_sscc(company_prefix: str, serial: int | None = None, extension_digit: int = 0) -> str:
    """Genera un SSCC de 18 dígitos: extensión(1) + prefijo GS1 + serial + control(1).

    - `company_prefix`: prefijo GS1 de la empresa (7-10 dígitos).
    - `serial`: referencia seriada; si es None se usa un valor basado en tiempo.
    - `extension_digit`: dígito de extensión logístico (0-9).
    """
    cp = "".join(c for c in str(company_prefix) if c.isdigit()) or "0000000"
    if serial is None:
        serial = int(time.time() * 1000) % (10 ** 12)
    body = f"{extension_digit % 10}{cp}"
    # Rellenar con el serial hasta 17 dígitos (extensión + prefijo + serial)
    pad = 17 - len(body)
    if pad < 1:
        body = body[:16]
        pad = 1
    body = body + str(serial).zfill(pad)[-pad:]
    body = body[:17]
    return body + str(gs1_check_digit(body))
