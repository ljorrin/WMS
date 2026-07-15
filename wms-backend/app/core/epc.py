"""
WMS Panamá — Codificación EPC (GS1 Tag Data Standard) — Fase 2 (hardware/RF/ZPL)
==================================================================================
Codifica/decodifica identificadores GS1 (GTIN+serie, SSCC) al EPC binario de
96 bits que se graba en tags RFID EPC Gen2 (UHF), según el GS1 Tag Data
Standard (TDS) — esquemas SGTIN-96 y SSCC-96. Es el mismo cálculo que hace la
herramienta pública de GS1 (https://www.gs1.org/services/epc-encoderdecoder):
a partir de un GTIN o SSCC + el GS1 Company Prefix real de la empresa, produce
el EPC en hex (para programar el tag) y en URI (para trazabilidad/logs).

Headers y tabla de partición (ancho en bits de Company Prefix vs. Item
Reference/Serial Reference) verificados contra la documentación pública de
GS1 (GS1 EPC Tag Data Standard — ref.gs1.org/standards/tds). No se adivinan:
- SGTIN-96 header = 0x30; 44 bits para repartir entre Company Prefix (M) e
  Item Reference (N) según partición 0-6; Serial Number = 38 bits fijos.
- SSCC-96  header = 0x31; 58 bits para repartir entre Company Prefix (M) y
  Serial Reference (N) según partición 0-6; 24 bits reservados (= 0) al final.

Puro cálculo de bits — sin dependencias externas ni acceso a BD.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.gs1 import gs1_check_digit, is_valid_gtin

SGTIN_96_HEADER = 0x30
SSCC_96_HEADER = 0x31

# dígitos del Company Prefix -> (valor de partición, bits de Company Prefix,
# bits del otro campo — Item Reference para SGTIN, Serial Reference para SSCC)
_SGTIN_PARTITIONS: dict[int, tuple[int, int, int]] = {
    12: (0, 40, 4),
    11: (1, 37, 7),
    10: (2, 34, 10),
    9: (3, 30, 14),
    8: (4, 27, 17),
    7: (5, 24, 20),
    6: (6, 20, 24),
}
_SSCC_PARTITIONS: dict[int, tuple[int, int, int]] = {
    12: (0, 40, 18),
    11: (1, 37, 21),
    10: (2, 34, 24),
    9: (3, 30, 28),
    8: (4, 27, 31),
    7: (5, 24, 34),
    6: (6, 20, 38),
}
_SGTIN_BY_PARTITION = {v[0]: (k, v[1], v[2]) for k, v in _SGTIN_PARTITIONS.items()}
_SSCC_BY_PARTITION = {v[0]: (k, v[1], v[2]) for k, v in _SSCC_PARTITIONS.items()}

SGTIN_SERIAL_BITS = 38
SGTIN_MAX_SERIAL = (1 << SGTIN_SERIAL_BITS) - 1


class EpcEncodingError(ValueError):
    """Error de codificación/decodificación EPC (payload inválido o fuera de rango)."""


def _bits(value: int, width: int) -> str:
    if value < 0 or value >= (1 << width):
        raise EpcEncodingError(f"El valor {value} no cabe en {width} bits.")
    return format(value, f"0{width}b")


def _company_prefix_partition(digits_len: int, table: dict[int, tuple[int, int, int]]) -> tuple[int, int, int]:
    if digits_len not in table:
        raise EpcEncodingError(
            f"Company Prefix debe tener entre 6 y 12 dígitos (recibido: {digits_len})."
        )
    return table[digits_len]


@dataclass(frozen=True)
class SgtinEpc:
    epc_hex: str
    epc_uri: str
    filter_value: int
    company_prefix: str
    item_reference: str
    serial: int
    gtin: str


@dataclass(frozen=True)
class SsccEpc:
    epc_hex: str
    epc_uri: str
    filter_value: int
    company_prefix: str
    serial_reference: str
    sscc: str


def encode_sgtin96(gtin: str, company_prefix: str, serial: int, filter_value: int = 1) -> SgtinEpc:
    """
    Codifica GTIN (8/12/13/14) + Company Prefix real + número de serie a EPC
    SGTIN-96. `filter_value` (0-7): 1=unidad de venta, 2=caja, 6=pallet/unit
    load (valores estándar GS1; ver docstring del módulo).
    """
    gtin = gtin.strip()
    if not is_valid_gtin(gtin):
        raise EpcEncodingError(f"GTIN inválido (dígito de control incorrecto): {gtin}")
    gtin14 = gtin.zfill(14)

    company_prefix = "".join(c for c in company_prefix if c.isdigit())
    partition, cp_bits, ir_bits = _company_prefix_partition(len(company_prefix), _SGTIN_PARTITIONS)

    indicator_digit = gtin14[0]
    cp_in_gtin = gtin14[1:1 + len(company_prefix)]
    if cp_in_gtin != company_prefix:
        raise EpcEncodingError(
            f"El GTIN {gtin14} no comienza con el Company Prefix {company_prefix} "
            f"(indicador + prefijo esperado: {indicator_digit}{company_prefix})."
        )
    item_reference_digits = indicator_digit + gtin14[1 + len(company_prefix):13]

    if not (0 <= filter_value <= 7):
        raise EpcEncodingError("filter_value debe estar entre 0 y 7.")
    if not (0 <= serial <= SGTIN_MAX_SERIAL):
        raise EpcEncodingError(f"El serial excede {SGTIN_SERIAL_BITS} bits (máx {SGTIN_MAX_SERIAL}).")

    bitstring = (
        _bits(SGTIN_96_HEADER, 8) + _bits(filter_value, 3) + _bits(partition, 3)
        + _bits(int(company_prefix), cp_bits) + _bits(int(item_reference_digits), ir_bits)
        + _bits(serial, SGTIN_SERIAL_BITS)
    )
    assert len(bitstring) == 96
    epc_hex = f"{int(bitstring, 2):024X}"
    uri = f"urn:epc:tag:sgtin-96:{filter_value}.{company_prefix}.{item_reference_digits}.{serial}"
    return SgtinEpc(
        epc_hex=epc_hex, epc_uri=uri, filter_value=filter_value,
        company_prefix=company_prefix, item_reference=item_reference_digits,
        serial=serial, gtin=gtin14,
    )


def decode_sgtin96(epc_hex: str) -> SgtinEpc:
    """Decodifica un EPC SGTIN-96 (24 caracteres hex) a sus componentes GS1."""
    epc_hex = epc_hex.strip().replace(" ", "")
    if len(epc_hex) != 24:
        raise EpcEncodingError("El EPC SGTIN-96 debe tener 24 caracteres hex (96 bits).")
    try:
        bits = f"{int(epc_hex, 16):096b}"
    except ValueError as exc:
        raise EpcEncodingError(f"EPC no es hexadecimal válido: {epc_hex}") from exc

    header = int(bits[0:8], 2)
    if header != SGTIN_96_HEADER:
        raise EpcEncodingError(f"Header 0x{header:02X} no corresponde a SGTIN-96 (0x{SGTIN_96_HEADER:02X}).")
    filter_value = int(bits[8:11], 2)
    partition = int(bits[11:14], 2)
    if partition not in _SGTIN_BY_PARTITION:
        raise EpcEncodingError(f"Valor de partición SGTIN-96 inválido: {partition}")
    cp_digits, cp_bits, ir_bits = _SGTIN_BY_PARTITION[partition]

    pos = 14
    cp_value = int(bits[pos:pos + cp_bits], 2)
    pos += cp_bits
    ir_value = int(bits[pos:pos + ir_bits], 2)
    pos += ir_bits
    serial = int(bits[pos:pos + SGTIN_SERIAL_BITS], 2)

    company_prefix = str(cp_value).zfill(cp_digits)
    item_reference_digits = str(ir_value).zfill(13 - cp_digits)
    indicator_digit = item_reference_digits[0]

    gtin_no_check = indicator_digit + company_prefix + item_reference_digits[1:]
    gtin14 = gtin_no_check + str(gs1_check_digit(gtin_no_check))

    uri = f"urn:epc:tag:sgtin-96:{filter_value}.{company_prefix}.{item_reference_digits}.{serial}"
    return SgtinEpc(
        epc_hex=epc_hex.upper(), epc_uri=uri, filter_value=filter_value,
        company_prefix=company_prefix, item_reference=item_reference_digits,
        serial=serial, gtin=gtin14,
    )


def encode_sscc96(sscc: str, company_prefix: str, filter_value: int = 0) -> SsccEpc:
    """Codifica un SSCC (18 dígitos) + Company Prefix real a EPC SSCC-96."""
    sscc = "".join(c for c in sscc if c.isdigit())
    if len(sscc) != 18:
        raise EpcEncodingError("El SSCC debe tener 18 dígitos.")
    if gs1_check_digit(sscc[:-1]) != int(sscc[-1]):
        raise EpcEncodingError(f"SSCC inválido (dígito de control incorrecto): {sscc}")

    company_prefix = "".join(c for c in company_prefix if c.isdigit())
    partition, cp_bits, sr_bits = _company_prefix_partition(len(company_prefix), _SSCC_PARTITIONS)

    extension_digit = sscc[0]
    cp_in_sscc = sscc[1:1 + len(company_prefix)]
    if cp_in_sscc != company_prefix:
        raise EpcEncodingError(
            f"El SSCC {sscc} no comienza con el Company Prefix {company_prefix} "
            f"(extensión + prefijo esperado: {extension_digit}{company_prefix})."
        )
    serial_reference_digits = extension_digit + sscc[1 + len(company_prefix):17]

    if not (0 <= filter_value <= 7):
        raise EpcEncodingError("filter_value debe estar entre 0 y 7.")

    bitstring = (
        _bits(SSCC_96_HEADER, 8) + _bits(filter_value, 3) + _bits(partition, 3)
        + _bits(int(company_prefix), cp_bits) + _bits(int(serial_reference_digits), sr_bits)
        + _bits(0, 24)  # reservado — debe ser cero (GS1 TDS)
    )
    assert len(bitstring) == 96
    epc_hex = f"{int(bitstring, 2):024X}"
    uri = f"urn:epc:tag:sscc-96:{filter_value}.{company_prefix}.{serial_reference_digits}"
    return SsccEpc(
        epc_hex=epc_hex, epc_uri=uri, filter_value=filter_value,
        company_prefix=company_prefix, serial_reference=serial_reference_digits, sscc=sscc,
    )


def decode_sscc96(epc_hex: str) -> SsccEpc:
    """Decodifica un EPC SSCC-96 (24 caracteres hex) a sus componentes GS1."""
    epc_hex = epc_hex.strip().replace(" ", "")
    if len(epc_hex) != 24:
        raise EpcEncodingError("El EPC SSCC-96 debe tener 24 caracteres hex (96 bits).")
    try:
        bits = f"{int(epc_hex, 16):096b}"
    except ValueError as exc:
        raise EpcEncodingError(f"EPC no es hexadecimal válido: {epc_hex}") from exc

    header = int(bits[0:8], 2)
    if header != SSCC_96_HEADER:
        raise EpcEncodingError(f"Header 0x{header:02X} no corresponde a SSCC-96 (0x{SSCC_96_HEADER:02X}).")
    filter_value = int(bits[8:11], 2)
    partition = int(bits[11:14], 2)
    if partition not in _SSCC_BY_PARTITION:
        raise EpcEncodingError(f"Valor de partición SSCC-96 inválido: {partition}")
    cp_digits, cp_bits, sr_bits = _SSCC_BY_PARTITION[partition]

    pos = 14
    cp_value = int(bits[pos:pos + cp_bits], 2)
    pos += cp_bits
    sr_value = int(bits[pos:pos + sr_bits], 2)
    # 24 bits reservados finales — ignorados (deben ser cero al codificar).

    company_prefix = str(cp_value).zfill(cp_digits)
    serial_reference_digits = str(sr_value).zfill(17 - cp_digits)
    extension_digit = serial_reference_digits[0]

    sscc_no_check = extension_digit + company_prefix + serial_reference_digits[1:]
    sscc = sscc_no_check + str(gs1_check_digit(sscc_no_check))

    uri = f"urn:epc:tag:sscc-96:{filter_value}.{company_prefix}.{serial_reference_digits}"
    return SsccEpc(
        epc_hex=epc_hex.upper(), epc_uri=uri, filter_value=filter_value,
        company_prefix=company_prefix, serial_reference=serial_reference_digits, sscc=sscc,
    )


def decode_epc96(epc_hex: str) -> SgtinEpc | SsccEpc:
    """Detecta el esquema por el header y decodifica (SGTIN-96 o SSCC-96)."""
    epc_hex_clean = epc_hex.strip().replace(" ", "")
    if len(epc_hex_clean) != 24:
        raise EpcEncodingError("El EPC debe tener 24 caracteres hex (96 bits).")
    header = int(epc_hex_clean[:2], 16)
    if header == SGTIN_96_HEADER:
        return decode_sgtin96(epc_hex_clean)
    if header == SSCC_96_HEADER:
        return decode_sscc96(epc_hex_clean)
    raise EpcEncodingError(f"Header 0x{header:02X} no reconocido (esperado SGTIN-96 0x30 o SSCC-96 0x31).")
