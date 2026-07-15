"""
WMS Panamá — Generación de etiquetas ZPL (Zebra) — Fase 2 del plan de implementación
======================================================================================
Genera plantillas ZPL II para impresoras térmicas Zebra (o compatibles): la
etiqueta logística estándar de pallet/bulto lleva un código de barras GS1-128
con la Application Identifier (AI) 00 = SSCC, más el texto legible, y
opcionalmente el comando ^RFW para grabar el EPC SSCC-96 (ver app.core.epc)
en el inlay RFID del label ("smart label" RFID+barcode combinado).

Sintaxis verificada contra la documentación pública de Zebra:
  - Code 128 / GS1-128 y el escape ">8" (FNC1) para Application Identifiers:
    docs.zebra.com/.../zpl-zpl-commands/r-zpl-bc.html
  - ^RFW (escritura RFID) y su relación con la estructura de bits del EPC:
    docs.zebra.com/.../zpl-rfid-zpl-rfid-commands/r-zpl-rfid-rf.html

No se ha probado contra una impresora física ni contra el emulador Zebra
(no hay hardware disponible en este entorno) — el ZPL generado sigue la
sintaxis documentada, pero se recomienda validarlo en un equipo real (o el
emulador "Labelary") antes de usarlo en producción.
"""

from __future__ import annotations

from app.core.epc import encode_sscc96
from app.core.gs1 import gs1_check_digit


class ZplGenerationError(ValueError):
    """Payload inválido para generar una etiqueta ZPL."""


def _validate_sscc(sscc: str) -> str:
    sscc = "".join(c for c in sscc if c.isdigit())
    if len(sscc) != 18:
        raise ZplGenerationError("El SSCC debe tener 18 dígitos.")
    if gs1_check_digit(sscc[:-1]) != int(sscc[-1]):
        raise ZplGenerationError(f"SSCC inválido (dígito de control incorrecto): {sscc}")
    return sscc


def build_sscc_pallet_label_zpl(
    sscc: str,
    company_prefix: str,
    description: str | None = None,
    encode_rfid: bool = False,
) -> tuple[str, str | None, str | None]:
    """
    Etiqueta logística de pallet/bulto (100x150mm a 203dpi ≈ 812x1218 dots):
    código de barras GS1-128 (AI 00 = SSCC), texto legible en formato GS1
    "(00) NNNNNNNNNNNNNNNNNN", y opcionalmente ^RFW para grabar el EPC
    SSCC-96 en el tag RFID embebido.

    Devuelve (zpl, epc_hex, epc_uri) — epc_hex/epc_uri son None si
    encode_rfid=False (etiqueta solo barcode, sin inlay RFID).
    """
    sscc = _validate_sscc(sscc)

    epc = None
    if encode_rfid:
        epc = encode_sscc96(sscc, company_prefix=company_prefix)

    human_readable = f"(00) {sscc}"
    desc_line = f"^FO40,40^A0N,40,40^FD{description}^FS" if description else ""
    rfid_block = f"^RFW,H^FD{epc.epc_hex}^FS\n" if epc else ""

    zpl = (
        "^XA\n"
        "^CI28\n"  # UTF-8
        "^PW812\n"  # ancho ~100mm @ 203dpi
        "^LL1218\n"  # largo ~150mm @ 203dpi
        f"{desc_line}\n"
        "^FO40,100^A0N,30,30^FDSSCC:^FS\n"
        f"^FO40,140^A0N,35,35^FD{human_readable}^FS\n"
        "^BY3,3,120\n"
        "^FO40,190^BCN,,N,N,N,A\n"
        f"^FD>>800{sscc}^FS\n"
        f"{rfid_block}"
        "^XZ"
    )
    return zpl, (epc.epc_hex if epc else None), (epc.epc_uri if epc else None)
