"""Permisos del módulo de bodega (RBAC sobre los grupos definidos en apps/usuarios/roles.py).

Segregación de funciones (informe, sección 3.1): quien aprueba no ejecuta.
Por eso Gerencia solo LEE en inventario: no registra ingresos, egresos ni mermas.
"""
from apps.usuarios.roles import rol_requerido

# Operaciones que modifican inventario: solo Bodega / Logística.
bodega_requerida = rol_requerido('bodega')

# Consultas de stock y documentos.
lectura_inventario = rol_requerido('bodega', 'gerencia', 'finanzas', 'supervisor')

# Cardex (historial de movimientos) y documentos con valorización:
# el Técnico tiene prohibido consultarlo.
lectura_cardex = rol_requerido('bodega', 'gerencia', 'finanzas')
