#!/usr/bin/env python3
"""
WMS Panamá — Gateway LLRP real (Fase 2 del plan de implementación)
=====================================================================
Se conecta VÍA LLRP (Low Level Reader Protocol, el estándar EPCglobal/GS1
para readers RFID fijos) a un reader físico y reenvía cada lectura de tag a
la API del WMS (POST /api/v1/hardware/tag-reads), donde se decodifica el EPC
(SGTIN-96/SSCC-96) y se resuelve el producto/ubicación. Es el reemplazo de
`scripts/rfid_reader_simulator.py` cuando SÍ hay hardware real conectado.

Usa la librería `sllurp` (cliente LLRP puro Python) contra sus clases
`LLRPReaderClient`/`LLRPReaderConfig` — verificadas por inspección directa del
paquete instalado (sllurp==3.0.5): el reporte de cada tag llega como un dict
con claves `EPC` (bytes hex), `AntennaID` (int) y `PeakRSSI` (int/float dBm).

IMPORTANTE — dónde correr este script:
El único requisito real es que ESTA máquina tenga conectividad de red al
reader (su IP suele ser link-local 169.254.x.x cuando está conectado por
cable Ethernet directo sin DHCP, p. ej. detrás del mismo switch TP-Link que
el reader). Si esta máquina también corre el backend del WMS (Docker), úsala
directamente con --api-host http://localhost:8000 (valor por defecto) — no
hace falta una segunda PC ni túneles.

Solo si el WMS corre en OTRA máquina (no alcanzable desde donde está el
reader), pasa --api-host apuntando a esa máquina por LAN/WiFi, o a un túnel
(p. ej. ngrok) si están en redes distintas. Los defaults de este script ya
coinciden con el hardware real registrado (reader FX9500 en 169.254.1.1:5084,
bodega WH-01, código READER-DOCK-01, 4 antenas) — conecta el cable/adaptador
Ethernet al switch del reader y corre el script sin argumentos.

Instalación (en esta máquina, además de las dependencias del backend):
    pip install -r requirements-rfid-gateway.txt

Uso (con el hardware real ya documentado, todo por defecto):
    python rfid_llrp_gateway.py

    # Correr por 30 segundos y salir (útil para una primera prueba):
    python rfid_llrp_gateway.py --duration 30

    # Contra un WMS en otra máquina/túnel:
    python rfid_llrp_gateway.py --api-host https://xxxx.ngrok-free.dev
"""

from __future__ import annotations

import argparse
import signal
import sys
import time

# La consola de Windows suele usar cp1252 por defecto, que no puede codificar los
# emojis usados en los mensajes de este script — forzamos UTF-8 en stdout/stderr.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx
from sllurp.llrp import LLRPReaderClient, LLRPReaderConfig


def _login(client: httpx.Client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _resolve_warehouse_id(client: httpx.Client, headers: dict, warehouse_code: str) -> str:
    resp = client.get("/api/v1/warehouses", headers=headers, params={"search": warehouse_code, "page_size": 50})
    resp.raise_for_status()
    for wh in resp.json().get("items", []):
        if wh.get("code") == warehouse_code:
            return wh["id"]
    raise SystemExit(f"❌ No se encontró la bodega con código '{warehouse_code}'.")


def _ensure_reader(
    client: httpx.Client, headers: dict, warehouse_id: str,
    reader_code: str, reader_ip: str, reader_port: int,
) -> str:
    resp = client.get("/api/v1/hardware/readers", headers=headers, params={"warehouse_id": warehouse_id})
    resp.raise_for_status()
    for r in resp.json().get("items", []):
        if r["code"] == reader_code:
            print(f"↩️  Reader existente en el WMS: {reader_code} ({r['id']})")
            return r["id"]

    resp = client.post(
        "/api/v1/hardware/readers", headers=headers,
        json={
            "warehouse_id": warehouse_id, "code": reader_code, "name": f"Reader físico {reader_code}",
            "ip_address": reader_ip, "port": reader_port,
        },
    )
    resp.raise_for_status()
    reader_id = resp.json()["id"]
    print(f"✅ Reader registrado en el WMS: {reader_code} ({reader_id})")
    return reader_id


def _ensure_antennas(client: httpx.Client, headers: dict, reader_id: str, antenna_numbers: list[int]) -> None:
    resp = client.get(f"/api/v1/hardware/readers/{reader_id}/antennas", headers=headers)
    resp.raise_for_status()
    existing = {a["antenna_number"] for a in resp.json().get("items", [])}
    for n in antenna_numbers:
        if n in existing:
            continue
        resp = client.post(
            f"/api/v1/hardware/readers/{reader_id}/antennas", headers=headers,
            json={"antenna_number": n, "name": f"Antena {n}"},
        )
        resp.raise_for_status()
        print(f"✅ Antena {n} registrada en el WMS.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-host", default="http://localhost:8000",
                         help="URL del WMS. Por defecto localhost:8000 (misma máquina que el backend Docker).")
    parser.add_argument("--email", default="admin@wmspanama.com")
    parser.add_argument("--password", default="Admin123!")
    parser.add_argument("--warehouse-code", default="WH-01")
    parser.add_argument("--reader-code", default="READER-DOCK-01",
                         help="Código con el que este reader se registra en el WMS.")
    parser.add_argument("--reader-ip", default="169.254.1.1",
                         help="IP LLRP real del reader (default: la del FX9500 confirmado por hardware).")
    parser.add_argument("--reader-port", type=int, default=5084)
    parser.add_argument("--antennas", default="1,2,3,4", help="Puertos de antena a habilitar, p. ej. 1,2,3,4")
    parser.add_argument("--duration", type=float, default=0, help="Segundos a correr (0 = indefinido, Ctrl+C para detener).")
    args = parser.parse_args()

    antenna_numbers = [int(a) for a in args.antennas.split(",")]

    print(f"🔎 Verificando que la API del WMS sea alcanzable en {args.api_host}...")
    # El header ngrok-skip-browser-warning evita la página de advertencia que
    # ngrok inyecta en el tier gratuito para requests que no vienen de un
    # navegador (inofensivo si --api-host no pasa por ngrok).
    with httpx.Client(
        base_url=args.api_host, timeout=10.0,
        headers={"ngrok-skip-browser-warning": "true"},
    ) as client:
        try:
            client.get("/api/v1/health/live").raise_for_status()
        except httpx.HTTPError as exc:
            raise SystemExit(
                f"❌ No se pudo alcanzar la API en {args.api_host}: {exc}\n"
                f"   Verifica que esta máquina esté en la misma red que el servidor del WMS "
                f"y que el firewall/puerto estén abiertos."
            )
        print("✅ API alcanzable.\n")

        headers = _login(client, args.email, args.password)
        warehouse_id = _resolve_warehouse_id(client, headers, args.warehouse_code)
        reader_id = _ensure_reader(client, headers, warehouse_id, args.reader_code, args.reader_ip, args.reader_port)
        _ensure_antennas(client, headers, reader_id, antenna_numbers)

        seen_counter = {"n": 0}

        def on_tag_report(_reader, tags: list[dict]) -> None:
            for tag in tags:
                epc_raw = tag.get("EPC") or tag.get("EPC-96")
                if not epc_raw:
                    continue
                epc_hex = (
                    epc_raw.decode("ascii").upper()
                    if isinstance(epc_raw, (bytes, bytearray))
                    else str(epc_raw).upper()
                )
                antenna_number = tag.get("AntennaID")
                rssi = tag.get("PeakRSSI")

                payload: dict = {"reader_code": args.reader_code, "epc_hex": epc_hex}
                if antenna_number is not None:
                    payload["antenna_number"] = int(antenna_number)
                if rssi is not None:
                    payload["rssi_dbm"] = float(rssi)

                try:
                    resp = client.post("/api/v1/hardware/tag-reads", headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    seen_counter["n"] += 1
                    print(
                        f"  📡 [{seen_counter['n']}] EPC={epc_hex} antena={antenna_number} rssi={rssi}dBm  "
                        f"→ scheme={data['epc_scheme']} gtin={data.get('gtin')} sscc={data.get('sscc')} "
                        f"product_id={data.get('product_id')}"
                    )
                except httpx.HTTPError as exc:
                    print(f"  ⚠️  Error enviando lectura a la API: {exc}")
                except RuntimeError as exc:
                    # El reader puede entregar un último reporte de tag por su reactor
                    # interno justo cuando este script ya está cerrando el cliente HTTP
                    # (fin de --duration o Ctrl+C) — no es un fallo real, solo se pierde
                    # esa última lectura puntual.
                    print(f"  ⚠️  Lectura descartada (cliente HTTP ya cerrado al terminar): {exc}")

        config = LLRPReaderConfig()
        config.antennas = antenna_numbers
        # sllurp exige que tx_power tenga una entrada por CADA antena configurada
        # (su default es {1: 0}, que solo cubre la antena 1) — 0 = potencia máxima
        # por defecto del reader.
        config.tx_power = {ant: 0 for ant in antenna_numbers}
        config.tag_content_selector["EnableAntennaID"] = True
        config.tag_content_selector["EnablePeakRSSI"] = True
        config.start_inventory = True
        config.reconnect = True
        # Sin esto, el reader por defecto acumula todas las lecturas y solo las
        # reporta al terminar el ROSpec (p. ej. al desconectar) — con esto reporta
        # cada tag en tiempo real, uno por uno.
        config.report_every_n_tags = 1

        print(f"📡 Conectando por LLRP a {args.reader_ip}:{args.reader_port}...")
        reader = LLRPReaderClient(args.reader_ip, args.reader_port, config=config)
        reader.add_tag_report_callback(on_tag_report)

        try:
            reader.connect()
        except Exception as exc:  # noqa: BLE001 — cualquier fallo de conexión LLRP debe ser diagnosticable
            raise SystemExit(
                f"❌ No se pudo conectar por LLRP al reader en {args.reader_ip}:{args.reader_port}: {exc}\n"
                f"   Verifica: el reader está encendido y accesible en esa IP/puerto desde ESTA máquina "
                f"(prueba 'ping {args.reader_ip}' y que el puerto {args.reader_port} responda), y que ningún "
                f"otro cliente LLRP (p. ej. la utilidad 'Reader Management') tenga la conexión abierta — "
                f"LLRP solo admite un cliente conectado a la vez."
            )

        print("✅ Conectado por LLRP. Leyendo tags (Ctrl+C para detener)...\n")

        def _stop(_signum, _frame):
            print(f"\n🛑 Deteniendo... ({seen_counter['n']} lecturas enviadas)")
            reader.disconnect()
            sys.exit(0)

        signal.signal(signal.SIGINT, _stop)

        if args.duration > 0:
            time.sleep(args.duration)
            # Pequeño margen para que cualquier reporte de tag ya en vuelo termine
            # de enviarse a la API antes de desconectar y cerrar el cliente HTTP.
            time.sleep(0.5)
            reader.disconnect()
            print(f"\n✅ Finalizado tras {args.duration}s. {seen_counter['n']} lecturas enviadas.")
        else:
            reader.join()


if __name__ == "__main__":
    main()
