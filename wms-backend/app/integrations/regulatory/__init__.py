"""Integraciones regulatorias de Panamá (ANA/SIGA y DGI).

Toda la lógica (construcción de DAM y de factura electrónica DGI con ITBMS) está
implementada en código. El envío real usa endpoints/credenciales parametrizados
por entorno (ver app/integrations/config.py). Sin configuración, los `submit_*`
devuelven `configured=False` sin llamar a sistemas externos.
"""
