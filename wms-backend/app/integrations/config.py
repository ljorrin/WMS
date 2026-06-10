"""
WMS Panamá — Configuración de integraciones (parametrizable por entorno)
=========================================================================
Lee credenciales/endpoints desde variables de entorno. Donde no haya valor,
queda como placeholder (None) y el adaptador correspondiente reporta
`configured=False`. NINGÚN secreto está hardcodeado.

Variables esperadas (configurar en despliegue):
  ERP:        ERP_BASE_URL, ERP_API_KEY, ERP_TYPE(sap|oracle|dynamics|odoo|generic)
  eCommerce:  ECOMMERCE_BASE_URL, ECOMMERCE_API_KEY, ECOMMERCE_PLATFORM
  Transporte: CARRIER_BASE_URL, CARRIER_API_KEY, CARRIER_NAME
  ANA/SIGA:   SIGA_BASE_URL, SIGA_API_KEY, SIGA_ENVIRONMENT(sandbox|production)
  DGI:        DGI_BASE_URL, DGI_API_KEY, DGI_RUC_EMISOR, DGI_ENVIRONMENT
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return v if v else None


@dataclass(frozen=True)
class EndpointConfig:
    name: str
    base_url: Optional[str]
    api_key: Optional[str]
    extra: dict

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @property
    def missing(self) -> list[str]:
        m = []
        if not self.base_url:
            m.append(f"{self.name}_BASE_URL")
        if not self.api_key:
            m.append(f"{self.name}_API_KEY")
        return m


def erp_config() -> EndpointConfig:
    return EndpointConfig("ERP", _env("ERP_BASE_URL"), _env("ERP_API_KEY"),
                          {"type": _env("ERP_TYPE") or "generic"})


def ecommerce_config() -> EndpointConfig:
    return EndpointConfig("ECOMMERCE", _env("ECOMMERCE_BASE_URL"), _env("ECOMMERCE_API_KEY"),
                          {"platform": _env("ECOMMERCE_PLATFORM") or "generic"})


def carrier_config() -> EndpointConfig:
    return EndpointConfig("CARRIER", _env("CARRIER_BASE_URL"), _env("CARRIER_API_KEY"),
                          {"name": _env("CARRIER_NAME") or "generic"})


def siga_config() -> EndpointConfig:
    return EndpointConfig("SIGA", _env("SIGA_BASE_URL"), _env("SIGA_API_KEY"),
                          {"environment": _env("SIGA_ENVIRONMENT") or "sandbox"})


def dgi_config() -> EndpointConfig:
    return EndpointConfig("DGI", _env("DGI_BASE_URL"), _env("DGI_API_KEY"),
                          {"ruc_emisor": _env("DGI_RUC_EMISOR"),
                           "environment": _env("DGI_ENVIRONMENT") or "sandbox"})
