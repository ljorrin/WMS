#!/usr/bin/env python3
"""
WMS Panamá — Aplicador idempotente de cableado de mejoras
==========================================================
Conecta los módulos Labor Management, Slotting Dinámico y Order Streaming
(waveless) en los 4 archivos COMPARTIDOS del backend, SIN duplicar si ya
están aplicados. Seguro de re-ejecutar tantas veces como haga falta
(p. ej. después de un `git checkout` que revierta los archivos versionados).

Uso:
    python scripts/apply_mejoras_wiring.py            # raíz = cwd (wms-backend)
    python scripts/apply_mejoras_wiring.py /ruta/wms-backend

Después de correrlo:  git add -A && git commit -m "wire labor+slotting+streaming"
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
changed: list[str] = []


def edit(rel: str, fn):
    p = ROOT / rel
    if not p.exists():
        print(f"  ⚠️  no existe: {rel} (omitido)")
        return
    src = p.read_text(encoding="utf-8")
    out = fn(src)
    if out != src:
        p.write_text(out, encoding="utf-8")
        changed.append(rel)
        print(f"  ✅ actualizado: {rel}")
    else:
        print(f"  ↩️  ya estaba cableado: {rel}")


# ── 1) app/core/exceptions.py ───────────────────────────────────────────────────
LABOR_EXC = '''

# ── Labor Management (FR-090…093) ───────────────────────────────────────────────

class LaborServiceError(WMSError):
    """Error genérico del servicio de gestión de mano de obra."""


class LaborStandardError(LaborServiceError):
    """Conflicto o invalidez en un estándar de labor."""


class LaborTaskStateError(LaborServiceError):
    """La tarea de labor no está en un estado válido para la operación."""
'''

SLOTTING_EXC = '''

# ── Slotting dinámico (FR-094…097) ──────────────────────────────────────────────

class SlottingServiceError(WMSError):
    """Error genérico del servicio de slotting."""


class SlottingPolicyError(SlottingServiceError):
    """Conflicto o invalidez en una política de slotting."""


class SlottingStateError(SlottingServiceError):
    """La recomendación de slotting no está en un estado válido."""
'''


def fix_exceptions(src: str) -> str:
    if "class LaborServiceError" not in src:
        src = src.rstrip() + "\n" + LABOR_EXC
    if "class SlottingServiceError" not in src:
        src = src.rstrip() + "\n" + SLOTTING_EXC
    return src


# ── 2) app/models/__init__.py ───────────────────────────────────────────────────
def fix_models_init(src: str) -> str:
    if "from app.models.labor import" not in src:
        src = src.replace(
            "from app.models.yms import Dock, YardAppointment\n",
            "from app.models.yms import Dock, YardAppointment\n"
            "from app.models.labor import LaborStandard, LaborTask\n",
        )
    if "from app.models.slotting import" not in src:
        src = src.replace(
            "from app.models.labor import LaborStandard, LaborTask\n",
            "from app.models.labor import LaborStandard, LaborTask\n"
            "from app.models.slotting import SlottingPolicy, SlottingRecommendation\n",
        )
    # __all__ entries (insert before the final closing bracket of __all__)
    add = []
    if '"Dock"' not in src:
        add.append('    "Dock", "YardAppointment",')
    if '"LaborStandard"' not in src:
        add.append('    "LaborStandard", "LaborTask",')
    if '"SlottingPolicy"' not in src:
        add.append('    "SlottingPolicy", "SlottingRecommendation",')
    if add:
        src = re.sub(r"\n\]\s*$", "\n" + "\n".join(add) + "\n]\n", src, count=1)
    return src


# ── 3) app/api/v1/router.py ─────────────────────────────────────────────────────
INCLUDES = {
    "labor": '\n# ── Labor Management (gestión de mano de obra) ───────────────────────────────\n'
             'api_router.include_router(labor.router, prefix="/labor", tags=["👷 Labor"])\n',
    "slotting": '\n# ── Slotting dinámico (ubicación óptima por rotación) ─────────────────────────\n'
                'api_router.include_router(slotting.router, prefix="/slotting", tags=["🎯 Slotting"])\n',
    "streaming": '\n# ── Order Streaming / Picking waveless ───────────────────────────────────────\n'
                 'api_router.include_router(streaming.router, prefix="/streaming", tags=["🌊 Streaming"])\n',
}


def fix_router(src: str) -> str:
    # a) ensure names are imported on the endpoints import line
    m = re.search(r"from app\.api\.v1\.endpoints import ([^\n]+)", src)
    if m:
        names = [n.strip() for n in m.group(1).split(",")]
        for mod in ("labor", "slotting", "streaming"):
            if mod not in names:
                names.append(mod)
        src = src[:m.start()] + "from app.api.v1.endpoints import " + ", ".join(names) + src[m.end():]
    # b) ensure include_router lines
    for mod, block in INCLUDES.items():
        if f"{mod}.router" not in src:
            src = src.rstrip() + "\n" + block
    return src


# ── 4) seeds/run_all.py ─────────────────────────────────────────────────────────
PERMS_BLOCK = '''
    # ── Labor Management ──
    ("labor:read",               "Ver Productividad/Labor",  "labor"),
    ("labor:standard:manage",    "Gestionar Estándares de Labor", "labor"),
    ("labor:task:manage",        "Gestionar Tareas de Labor","labor"),
    ("labor:task:execute",       "Ejecutar Tareas de Labor", "labor"),

    # ── Slotting dinámico ──
    ("slotting:read",            "Ver Slotting",             "slotting"),
    ("slotting:run",             "Ejecutar Análisis de Slotting", "slotting"),
    ("slotting:manage",          "Gestionar Slotting",       "slotting"),
'''


def fix_seeds(src: str) -> str:
    if '"labor:read"' not in src:
        # insert after the ai:optimization:run permission tuple
        anchor = '    ("ai:optimization:run",      "Ejecutar Optimizaciones",  "ai"),\n'
        if anchor in src:
            src = src.replace(anchor, anchor + PERMS_BLOCK, 1)
    # Supervisor role
    if "labor:standard:manage" in src and 'sup-role-done' not in src:
        sup = ('            "master:product:read", "admin:audit:read", "admin:reports:export",\n'
               '        ],')
        if sup in src and '"slotting:manage"' not in src:
            src = src.replace(
                sup,
                '            "master:product:read", "admin:audit:read", "admin:reports:export",\n'
                '            "labor:read", "labor:standard:manage", "labor:task:manage", "labor:task:execute",\n'
                '            "slotting:read", "slotting:run", "slotting:manage",\n'
                '        ],', 1)
    # Operador role
    op = ('            "outbound:order:read", "outbound:picking:execute", "outbound:packing:execute",\n'
          '            "master:product:read",\n        ],')
    if op in src and '"labor:task:execute"' in src and op.replace('"master:product:read",\n', '"master:product:read",\n            "labor:read"') not in src:
        if '            "labor:read", "labor:task:execute",\n        ],' not in src:
            src = src.replace(
                op,
                '            "outbound:order:read", "outbound:picking:execute", "outbound:packing:execute",\n'
                '            "master:product:read",\n'
                '            "labor:read", "labor:task:execute",\n        ],', 1)
    # Analista IA role
    ana = ('            "ai:insights:read", "ai:forecast:read", "ai:optimization:run",\n'
           '            "admin:reports:export",\n        ],')
    if ana in src:
        src = src.replace(
            ana,
            '            "ai:insights:read", "ai:forecast:read", "ai:optimization:run",\n'
            '            "slotting:read", "slotting:run",\n'
            '            "admin:reports:export",\n        ],', 1)
    return src


def main():
    print(f"Aplicando cableado de mejoras en: {ROOT}\n")
    edit("app/core/exceptions.py", fix_exceptions)
    edit("app/models/__init__.py", fix_models_init)
    edit("app/api/v1/router.py", fix_router)
    edit("seeds/run_all.py", fix_seeds)
    print()
    if changed:
        print("Archivos modificados:", ", ".join(changed))
        print("Siguiente paso:  git add -A && git commit -m 'wire labor+slotting+streaming'")
    else:
        print("Nada que hacer: todo el cableado ya estaba aplicado.")


if __name__ == "__main__":
    main()
