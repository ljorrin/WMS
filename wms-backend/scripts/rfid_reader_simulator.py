#!/usr/bin/env python3
"""
WMS Panamá — Simulador de Reader/Antena RFID (Fase 2 del plan de implementación)
==================================================================================
No hay hardware RFID físico disponible en este entorno de desarrollo. Este
script simula lo que un reader fijo (p. ej. Zebra FX9600, Impinj Speedway) +
su gateway LLRP enviarían a la API por cada tag detectado: un EPC (SGTIN-96 o
SSCC-96, codificado con app.core.epc igual que se grabaría en un tag real vía
ZPL ^RFW) más el RSSI que reportaría la antena — como si un pallet o una caja
cruzara el campo de una antena en un portal de dock.

No reemplaza probar contra hardware real: es la manera honesta de ejercitar el
pipeline completo (registro de reader/antena → ingesta → decodificación EPC →
resolución de producto/ubicación) sin adivinar comportamiento de firmware.

Uso:
  docker compose exec api python scripts/rfid_reader_simulator.py \\
      --warehouse-code WH-01 --reader-code READER-DOCK-01 --antenna-number 1 \\
      --company-prefix 0614141 --gtin 7501234567892 --n-reads 8 --sweep-delay 0.3

  # SSCC (pallet) en vez de SGTIN (unidad/caja):
  docker compose exec api python scripts/rfid_reader_simulator.py \\
      --warehouse-code WH-01 --reader-code READER-DOCK-01 --antenna-number 1 \\
      --company-prefix 0614141 --sscc 300614141000000018 --n-reads 5

Requiere: el warehouse ya debe existir (usa el código real de tu seed); el API
corriendo y accesible en --host.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from app.core.epc import encode_sgtin96, encode_sscc96
from app.core.gs1 import generate_sscc, is_valid_gtin


def _login(client: httpx.Client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _resolve_warehouse_id(client: httpx.Client, headers: dict, warehouse_code: str) -> str:
    resp = client.get("/api/v1/warehouses", headers=headers, params={"search": warehouse_code, "page_size": 50})
    resp.raise_for_status()
    for wh in resp.json().get("items", []):
        if wh.get("code") == warehouse_code:
            return wh["id"]
    raise SystemExit(f"No se encontró la bodega con código '{warehouse_code}'.")


def _ensure_reader(client: httpx.Client, headers: dict, warehouse_id: str, reader_code: str) -> str:
    resp = client.get("/api/v1/hardware/readers", headers=headers, params={"warehouse_id": warehouse_id})
    resp.raise_for_status()
    for r in resp.json().get("items", []):
        if r["code"] == reader_code:
            print(f"↩️  Reader existente: {reader_code} ({r['id']})")
            return r["id"]

    resp = client.post(
        "/api/v1/hardware/readers", headers=headers,
        json={
            "warehouse_id": warehouse_id, "code": reader_code, "name": f"Reader simulado {reader_code}",
            "vendor": "zebra", "model": "FX9600 (simulado)", "ip_address": "192.168.10.50",
            "port": 5084,
        },
    )
    resp.raise_for_status()
    reader_id = resp.json()["id"]
    print(f"✅ Reader registrado: {reader_code} ({reader_id})")
    return reader_id


def _ensure_antenna(client: httpx.Client, headers: dict, reader_id: str, antenna_number: int) -> None:
    resp = client.get(f"/api/v1/hardware/readers/{reader_id}/antennas", headers=headers)
    resp.raise_for_status()
    if any(a["antenna_number"] == antenna_number for a in resp.json().get("items", [])):
        print(f"↩️  Antena existente: puerto {antenna_number}")
        return
    resp = client.post(
        f"/api/v1/hardware/readers/{reader_id}/antennas", headers=headers,
        json={"antenna_number": antenna_number, "name": f"Antena {antenna_number} (simulada)", "transmit_power_dbm": 27.0},
    )
    resp.raise_for_status()
    print(f"✅ Antena registrada: puerto {antenna_number}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--email", default="admin@wmspanama.com")
    parser.add_argument("--password", default="Admin123!")
    parser.add_argument("--warehouse-code", required=True)
    parser.add_argument("--reader-code", required=True)
    parser.add_argument("--antenna-number", type=int, default=1)
    parser.add_argument("--company-prefix", required=True, help="GS1 Company Prefix real (6-12 dígitos).")
    parser.add_argument("--gtin", help="GTIN de la unidad/caja a simular (EPC SGTIN-96).")
    parser.add_argument("--sscc", help="SSCC del pallet a simular (EPC SSCC-96). Si se omite y no hay --gtin, se genera uno.")
    parser.add_argument("--n-reads", type=int, default=5, help="Cuántas veces \"lee\" el tag la antena (simula el barrido RF).")
    parser.add_argument("--sweep-delay", type=float, default=0.2, help="Segundos entre lecturas simuladas.")
    args = parser.parse_args()

    if args.gtin and not is_valid_gtin(args.gtin):
        raise SystemExit(f"GTIN inválido: {args.gtin}")

    if args.gtin:
        epc = encode_sgtin96(args.gtin, company_prefix=args.company_prefix, serial=random.randint(1, 999_999), filter_value=2)
        tag_desc = f"SGTIN-96 (GTIN {args.gtin})"
    else:
        sscc = args.sscc or generate_sscc(args.company_prefix)
        epc = encode_sscc96(sscc, company_prefix=args.company_prefix, filter_value=6)
        tag_desc = f"SSCC-96 (SSCC {sscc})"

    print(f"🏷️  Tag simulado: {tag_desc} → EPC {epc.epc_hex} ({epc.epc_uri})")

    with httpx.Client(base_url=args.host, timeout=10.0) as client:
        headers = _login(client, args.email, args.password)
        warehouse_id = _resolve_warehouse_id(client, headers, args.warehouse_code)
        reader_id = _ensure_reader(client, headers, warehouse_id, args.reader_code)
        _ensure_antenna(client, headers, reader_id, args.antenna_number)

        print(f"\n📡 Simulando {args.n_reads} lecturas de la antena {args.antenna_number}...")
        for i in range(args.n_reads):
            rssi = round(random.uniform(-70.0, -40.0), 1)  # rango típico UHF EPC Gen2 en campo cercano
            resp = client.post(
                "/api/v1/hardware/tag-reads", headers=headers,
                json={
                    "reader_code": args.reader_code, "antenna_number": args.antenna_number,
                    "epc_hex": epc.epc_hex, "rssi_dbm": rssi,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            print(
                f"  [{i + 1}/{args.n_reads}] RSSI={rssi}dBm  scheme={data['epc_scheme']}  "
                f"gtin={data.get('gtin')}  sscc={data.get('sscc')}  product_id={data.get('product_id')}"
            )
            time.sleep(args.sweep_delay)

    print("\n✅ Simulación completa.")


if __name__ == "__main__":
    main()
