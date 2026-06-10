"""Integraciones externas del WMS (ERP, eCommerce, transporte, regulatorio).

Todas las integraciones se implementan completas a nivel de código. Las
credenciales y endpoints se parametrizan por variables de entorno (ver
`app/integrations/config.py`). Cuando una integración no está configurada,
los adaptadores devuelven un resultado `configured=False` SIN realizar llamadas
externas, de modo que el sistema sigue funcionando sin la credencial real.
"""
