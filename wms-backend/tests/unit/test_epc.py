"""
Tests de codificación EPC GS1 (SGTIN-96 / SSCC-96) — Fase 2 (hardware/RF/ZPL).
Puro cálculo de bits, sin BD. Verifica: estructura de bits (header/filter/
partición), round-trip encode→decode, y detección de payloads inválidos.
"""
import pytest

from app.core.epc import (
    EpcEncodingError,
    SGTIN_96_HEADER,
    SSCC_96_HEADER,
    decode_epc96,
    decode_sgtin96,
    decode_sscc96,
    encode_sgtin96,
    encode_sscc96,
)
from app.core.gs1 import generate_sscc, is_valid_gtin


def _valid_gtin13(company_prefix: str, item_ref: str) -> str:
    """Construye un GTIN-13 válido: indicador(0) + prefijo + item_ref + control."""
    from app.core.gs1 import gs1_check_digit
    body = "0" + company_prefix + item_ref
    return body + str(gs1_check_digit(body))


class TestSgtin96:
    def test_encode_estructura_de_bits(self):
        gtin = _valid_gtin13("0614141", "12345")  # prefijo 7 dígitos → partición 5
        epc = encode_sgtin96(gtin, company_prefix="0614141", serial=1)

        assert len(epc.epc_hex) == 24
        assert int(epc.epc_hex, 16).bit_length() <= 96
        header = int(epc.epc_hex[:2], 16)
        assert header == SGTIN_96_HEADER == 0x30
        bits = f"{int(epc.epc_hex, 16):096b}"
        assert int(bits[8:11], 2) == 1  # filter_value default
        assert int(bits[11:14], 2) == 5  # partición para prefijo de 7 dígitos
        assert epc.epc_uri.startswith("urn:epc:tag:sgtin-96:1.0614141.")

    def test_roundtrip_todas_las_particiones(self):
        # Un prefijo por cada longitud (6 a 12 dígitos) — cubre las 7 particiones.
        casos = [
            ("614141", "123456"),
            ("0614141", "12345"),
            ("00614141", "1234"),
            ("000614141", "123"),
            ("0000614141", "12"),
            ("00000614141", "1"),
            ("000000614141", ""),
        ]
        for company_prefix, item_ref in casos:
            gtin = _valid_gtin13(company_prefix, item_ref)
            assert is_valid_gtin(gtin)
            for serial in (0, 1, 999, 274_877_906_943):  # 2^38-1 = máx serial
                epc = encode_sgtin96(gtin, company_prefix=company_prefix, serial=serial, filter_value=2)
                decoded = decode_sgtin96(epc.epc_hex)
                assert decoded.gtin == gtin.zfill(14)
                assert decoded.serial == serial
                assert decoded.filter_value == 2
                assert decoded.company_prefix == company_prefix

    def test_serial_fuera_de_rango(self):
        gtin = _valid_gtin13("0614141", "12345")
        with pytest.raises(EpcEncodingError):
            encode_sgtin96(gtin, company_prefix="0614141", serial=2 ** 38)
        with pytest.raises(EpcEncodingError):
            encode_sgtin96(gtin, company_prefix="0614141", serial=-1)

    def test_gtin_invalido_rechazado(self):
        with pytest.raises(EpcEncodingError):
            encode_sgtin96("0012345678901", company_prefix="0012345", serial=1)  # control incorrecto

    def test_company_prefix_no_coincide_con_gtin(self):
        gtin = _valid_gtin13("0614141", "12345")
        with pytest.raises(EpcEncodingError):
            encode_sgtin96(gtin, company_prefix="9999999", serial=1)

    def test_company_prefix_longitud_invalida(self):
        gtin = _valid_gtin13("0614141", "12345")
        with pytest.raises(EpcEncodingError):
            encode_sgtin96(gtin, company_prefix="12345", serial=1)  # 5 dígitos: fuera de 6-12

    def test_decode_header_incorrecto(self):
        sscc_epc = encode_sscc96(generate_sscc("0614141", serial=1), company_prefix="0614141")
        with pytest.raises(EpcEncodingError):
            decode_sgtin96(sscc_epc.epc_hex)  # header SSCC, no SGTIN

    def test_decode_longitud_invalida(self):
        with pytest.raises(EpcEncodingError):
            decode_sgtin96("3000")


class TestSscc96:
    def test_encode_estructura_de_bits(self):
        sscc = generate_sscc("0614141", serial=42)
        epc = encode_sscc96(sscc, company_prefix="0614141")

        assert len(epc.epc_hex) == 24
        header = int(epc.epc_hex[:2], 16)
        assert header == SSCC_96_HEADER == 0x31
        bits = f"{int(epc.epc_hex, 16):096b}"
        assert int(bits[11:14], 2) == 5  # partición para prefijo de 7 dígitos
        assert bits[-24:] == "0" * 24  # 24 bits reservados en cero
        assert epc.epc_uri.startswith("urn:epc:tag:sscc-96:0.0614141.")

    def test_roundtrip_todas_las_particiones(self):
        prefijos = ["614141", "0614141", "00614141", "000614141", "0000614141", "00000614141", "000000614141"]
        for company_prefix in prefijos:
            sscc = generate_sscc(company_prefix, serial=12345, extension_digit=3)
            epc = encode_sscc96(sscc, company_prefix=company_prefix, filter_value=6)
            decoded = decode_sscc96(epc.epc_hex)
            assert decoded.sscc == sscc
            assert decoded.company_prefix == company_prefix
            assert decoded.filter_value == 6

    def test_sscc_invalido_rechazado(self):
        sscc = generate_sscc("0614141", serial=1)
        bad = sscc[:-1] + str((int(sscc[-1]) + 1) % 10)  # corrompe el dígito de control
        with pytest.raises(EpcEncodingError):
            encode_sscc96(bad, company_prefix="0614141")

    def test_company_prefix_no_coincide(self):
        sscc = generate_sscc("0614141", serial=1)
        with pytest.raises(EpcEncodingError):
            encode_sscc96(sscc, company_prefix="9999999")


class TestDecodeEpc96Generico:
    def test_detecta_sgtin(self):
        gtin = _valid_gtin13("0614141", "12345")
        epc = encode_sgtin96(gtin, company_prefix="0614141", serial=7)
        decoded = decode_epc96(epc.epc_hex)
        assert decoded.gtin == gtin.zfill(14)

    def test_detecta_sscc(self):
        sscc = generate_sscc("0614141", serial=7)
        epc = encode_sscc96(sscc, company_prefix="0614141")
        decoded = decode_epc96(epc.epc_hex)
        assert decoded.sscc == sscc

    def test_header_desconocido(self):
        # header 0xFF no es ni SGTIN-96 ni SSCC-96
        with pytest.raises(EpcEncodingError):
            decode_epc96("FF" + "0" * 22)
