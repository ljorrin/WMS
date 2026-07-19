# Hardware RFID/RF + Etiquetas ZPL — Fase 2 del plan de implementación

Reporte basado en evidencia (metodología "nada asumido" — CLAUDE.md): distingue
lo verificado ejecutando de lo que queda pendiente por falta de hardware físico.

## Qué se construyó

| Pieza | Archivo | Estado |
|---|---|---|
| Codificación/decodificación GS1 EPC (SGTIN-96, SSCC-96) | `app/core/epc.py` | ✅ Verificado: 15 tests unitarios, round-trip en las 7 particiones GS1 (Company Prefix 6-12 dígitos) |
| Modelo de topología física (reader → antena → tag read) | `app/models/rfid.py` + migración `rfid001` | ✅ Verificado: migración aplicada contra PostgreSQL 16 real |
| Servicio de registro/ingesta | `app/services/rfid_service.py` | ✅ Verificado: 6 tests de integración contra PostgreSQL real |
| Generación de etiquetas ZPL (GS1-128 + RFID `^RFW`) | `app/services/zpl_service.py` | ✅ Verificado: 5 tests unitarios (estructura del ZPL) |
| Endpoints REST | `app/api/v1/endpoints/hardware.py` (`/api/v1/hardware/*`) | ✅ Verificado: smoke test manual vía curl (login real → generar ZPL, dashboard, listar readers) |
| Simulador de reader/antena/tag | `scripts/rfid_reader_simulator.py` | ✅ Verificado: corrida real end-to-end (login → registrar reader/antena → 3 lecturas ingeridas y decodificadas) |
| Permisos | `hardware:read`, `hardware:manage`, `hardware:ingest` en `seeds/run_all.py` | ✅ Sembrados |

## Por qué esta arquitectura (y qué NO se construyó)

Un reader RFID fijo (Zebra FX9600, Impinj Speedway, etc.) habla **LLRP** (Low
Level Reader Protocol, el estándar EPCglobal/GS1) con un gateway/middleware
dedicado — **no** con una API HTTP request/response como FastAPI. Implementar
el protocolo LLRP binario dentro de este proceso sería:
1. Trabajo no verificable sin el hardware/firmware real (alto riesgo de
   "adivinar" comportamiento).
2. Una responsabilidad distinta (un cliente LLRP de larga duración, con su
   propio ciclo de vida de conexión TCP persistente) que no encaja en el
   modelo request/response de una API REST.

Por eso el límite de esta fase es el **punto de ingesta** (`POST
/api/v1/hardware/tag-reads`) que ese gateway (o cualquier reader con firmware
que soporte webhooks HTTP, como varios modelos Zebra/Impinj recientes) llamaría
por cada lectura. `scripts/rfid_reader_simulator.py` reemplaza al gateway/
hardware real para poder probar el pipeline completo (decodificación EPC,
resolución de producto por GTIN, atribución a ubicación vía antena) sin tener
el equipo físico.

**Pendiente explícito** (requiere hardware o un entorno de staging con él):
- Probar el ZPL generado contra una impresora Zebra real (o el emulador
  "Labelary") — la sintaxis de `^BC`/`^RFW` está verificada contra la
  documentación pública de Zebra, pero no contra un renderizado real.
- Ejecutar `scripts/rfid_llrp_gateway.py` contra el reader físico real (ver
  abajo) — el script y sus defaults ya están listos, solo falta correrlo con
  el hardware conectado.
- Calibración de potencia de antena (`transmit_power_dbm`) y lógica de
  deduplicación de lecturas repetidas (un tag cruzando un portal genera
  decenas de `RfidTagRead` por segundo; hoy se persisten todas — falta una
  ventana de deduplicación si el volumen en producción lo amerita).

## Gateway LLRP real — listo para correr en esta máquina

Hardware confirmado: reader Motorola/Zebra **FX9500** (firmware 1.5.4.348,
MAC `C4:7D:CC:00:90:13`) en `169.254.1.1:5084`, 4 antenas, conectado a un
switch TP-Link TL-SF1008D sin WiFi.

`scripts/rfid_llrp_gateway.py` NO requiere una segunda máquina — solo
requiere que la máquina donde corre tenga conectividad de red (Ethernet) al
switch del reader. Sus defaults ya coinciden con el hardware real (reader
code `READER-DOCK-01`, bodega `WH-01`, IP `169.254.1.1:5084`, antenas
`1,2,3,4`, `--api-host http://localhost:8000`), así que una vez que esta
máquina esté conectada físicamente al switch (p. ej. vía adaptador
USB-Ethernet), correrlo es:
```
pip install -r requirements-rfid-gateway.txt
python rfid_llrp_gateway.py
```
Solo hace falta pasar `--api-host` distinto (LAN o túnel) si el backend del
WMS corre en una máquina que el reader no puede alcanzar directamente.
**Aún no ejecutado contra el hardware real** — pendiente de que la máquina
se conecte físicamente al switch del reader.

## Bug real encontrado y corregido

`RfidService.ingest_tag_read` resolvía el producto por GTIN convirtiendo el
GTIN-14 decodificado a GTIN-13 con `gtin.lstrip("0").zfill(13)` — esto quita
**todos** los ceros a la izquierda en vez de exactamente el dígito indicador,
corrompiendo el valor cuando el Company Prefix también empieza en cero (caso
nada raro: muchos prefijos GS1 asignados en Panamá empiezan con "06...").
Corregido a `gtin[1:]` (quitar exactamente 1 carácter). Encontrado ejecutando
`tests/integration_db/test_rfid_hardware.py` contra PostgreSQL real.
