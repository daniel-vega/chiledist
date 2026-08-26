"""Versión del paquete — módulo hoja sin dependencias internas.

Aislado de ``__init__.py`` para que ``domain/persistence.py`` (y cualquier
otro módulo de capa) pueda leer ``__version__`` sin importar el paquete
raíz ``chiledist`` (que a su vez importa todas las capas) y así evitar un
ciclo de import.
"""

__version__ = "0.2.0"
