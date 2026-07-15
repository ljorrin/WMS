"""Tests de generación de ZPL (Fase 2 — hardware/RF/ZPL). Puro string, sin BD."""
import pytest

from app.core.gs1 import generate_sscc
from app.services.zpl_service import ZplGenerationError, build_sscc_pallet_label_zpl


class TestSsccPalletLabel:
    def test_estructura_basica(self):
        sscc = generate_sscc("0614141", serial=1)
        zpl, epc_hex, epc_uri = build_sscc_pallet_label_zpl(sscc, company_prefix="0614141")

        assert zpl.startswith("^XA")
        assert zpl.strip().endswith("^XZ")
        assert f">>800{sscc}^FS" in zpl  # GS1-128: FNC1 (>8) + AI 00 (SSCC) + valor
        assert f"(00) {sscc}" in zpl  # texto legible en formato GS1
        assert "^RFW" not in zpl  # sin RFID por defecto
        assert epc_hex is None and epc_uri is None

    def test_con_descripcion(self):
        sscc = generate_sscc("0614141", serial=2)
        zpl, _, _ = build_sscc_pallet_label_zpl(sscc, company_prefix="0614141", description="Pallet Arroz 5kg")
        assert "Pallet Arroz 5kg" in zpl

    def test_con_rfid_incluye_epc(self):
        sscc = generate_sscc("0614141", serial=3)
        zpl, epc_hex, epc_uri = build_sscc_pallet_label_zpl(
            sscc, company_prefix="0614141", encode_rfid=True,
        )
        assert epc_hex is not None and len(epc_hex) == 24
        assert epc_uri is not None and epc_uri.startswith("urn:epc:tag:sscc-96:")
        assert f"^RFW,H^FD{epc_hex}^FS" in zpl

    def test_sscc_invalido_rechazado(self):
        with pytest.raises(ZplGenerationError):
            build_sscc_pallet_label_zpl("123", company_prefix="0614141")

    def test_sscc_control_incorrecto(self):
        sscc = generate_sscc("0614141", serial=4)
        bad = sscc[:-1] + str((int(sscc[-1]) + 1) % 10)
        with pytest.raises(ZplGenerationError):
            build_sscc_pallet_label_zpl(bad, company_prefix="0614141")
