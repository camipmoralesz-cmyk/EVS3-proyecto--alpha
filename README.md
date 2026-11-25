# ERP Logístico FYAG SpA — Proyecto Alpha

Sistema web de gestión logística para **Frío y Agroindustria SpA (FYAG)**, empresa de refrigeración, climatización y servicios agroindustriales de Chillán. Controla el inventario de bodega con un Cardex inmutable, el ingreso de documentos tributarios con costo PMP, los despachos a obras con firma digital, el restock aprobado por Finanzas y la evaluación financiera de cada proyecto.

---

## Índice

1. [Descripción general](#1-descripción-general)
2. [Manual de implementación técnica](#2-manual-de-implementación-técnica)
3. [Manual de usabilidad por rol](#3-manual-de-usabilidad-por-rol)
4. [Guía de flujos operativos](#4-guía-de-flujos-operativos)
5. [Estructura del proyecto](#5-estructura-del-proyecto)

---

## 1. Descripción general

| Módulo | Qué resuelve |
|---|---|
| **Catálogo** (`apps/catalogo`) | Artículos con código interno y de barras, categoría, ubicación y sector de bodega, umbrales de stock mínimo y crítico, precio de lista y descripción. Los artículos no se borran: se desactivan. |
| **Entidades** (`apps/entidades`) | Fichas de proveedores y mandantes (clientes) con RUT validado, región, comuna, ciudad, representante legal, contactos y cuentas bancarias. |
| **Inventario** (`apps/inventario`) | Ingreso de facturas, boletas, guías y notas de crédito; despachos a obra; mermas y devoluciones; inventario físico; restock. Todo cambio de stock pasa por un único punto de escritura (`registrar_movimiento()`). |
| **Obras** (`apps/obras`) | Obras y servicios del Anexo C, solicitudes de materiales, hojas de servicio (horas hombre) y evaluación de rentabilidad. |
| **Finanzas** (`apps/finanzas`) | Panel financiero, facturas, pagos a proveedores, presupuestos de obras y aprobación de restock. |
| **Auditoría** (`apps/auditoria`) | Cardex inmutable (append-only), bitácora de cambios, registro de accesos y exportación a Excel y PDF. |
| **Core / Usuarios** (`apps/core`, `apps/usuarios`) | Dashboard gerencial, alertas de stock, aprobación de actas, login por cuenta y control de acceso por rol (RBAC). |

**Principios de diseño**

- **Cardex inalterable:** los movimientos no se editan ni se eliminan; un error se corrige con un contra-asiento.
- **Segregación de funciones:** quien aprueba no ejecuta. Bodega mueve stock, Finanzas aprueba presupuestos y Gerencia audita.
- **Transacciones atómicas:** un documento o un despacho se registra completo o no se registra.

**Tecnologías:** Python 3.12 o superior, Django 6.1, PostgreSQL (o SQLite en desarrollo), Bootstrap 5.3, `fpdf2` y `reportlab` (PDF) y `openpyxl` (Excel).

---

## 2. Manual de implementación técnica

### 2.1 Requisitos

- Python 3.12 o superior y `pip`.
- Git.
- PostgreSQL 14 o superior instalado localmente. Para desarrollo se puede usar SQLite sin instalar nada más.

### 2.2 Instalación del entorno virtual

```bash
git clone <url-del-repositorio>
cd EVS3-proyecto--alpha

python -m venv venv
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 2.3 Variables de entorno (`.env`)

Copie `.env.example` como `.env` en la raíz del proyecto y complételo. El archivo `.env` está en `.gitignore` y **nunca** debe subirse al repositorio.

**Seguridad y dominios**

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `SECRET_KEY` | Clave de desarrollo (solo si `DEBUG=True`) | Clave secreta de Django. Con `DEBUG=False` es obligatoria: si falta, el sistema no arranca. |
| `DEBUG` | `True` | Modo depuración. Acepta `true`, `1` o `yes`; cualquier otro valor lo desactiva. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Dominios desde los que se puede acceder, separados por coma. |

```env
SECRET_KEY=una-clave-larga-y-aleatoria
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

**Base de datos**

La base de datos se elige según las variables definidas:

| Variables | Base de datos |
|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL local |
| Sin `DB_NAME` | SQLite local (`db.sqlite3`) |

**PostgreSQL local**

```env
DB_NAME=proyecto_alpha
DB_USER=postgres
DB_PASSWORD=clave_local
DB_HOST=127.0.0.1
DB_PORT=5432
```

Antes de migrar, cree la base: `createdb proyecto_alpha` (o desde pgAdmin).

**SQLite local**

Si no existe `.env` o no define `DB_NAME`, el sistema usa `db.sqlite3` en la raíz del proyecto. No requiere instalar nada adicional.

### 2.4 Migraciones

```bash
python manage.py migrate
python manage.py check
```

### 2.5 Roles y usuarios demo

```bash
python manage.py crear_roles --demo
```

Crea los grupos de roles y, con `--demo`, un usuario de prueba por rol (clave `Alpha2026!`). Sin `--demo` solo crea los grupos.

Para un administrador del panel de Django (`/admin/`): `python manage.py createsuperuser`.

### 2.6 Datos de prueba

Ejecute los comandos **en este orden** (cada uno se puede volver a ejecutar sin duplicar datos):

```bash
python manage.py crear_roles --demo     # 1. roles y usuarios demo
python manage.py poblar_datos_prueba    # 2. proveedores, categorías, artículos y una solicitud de despacho
python manage.py poblar_obras           # 3. mandante, obras y usuarios de obras
python manage.py poblar_demo_etapa5     # 4. factura y movimientos de ejemplo para Finanzas
```

- `poblar_datos_prueba` crea la solicitud de despacho de ejemplo solo si ya existe el usuario `supervisor` (paso 1).
- `poblar_demo_etapa5` registra sus movimientos a nombre de un superusuario, que crea el paso 3 (`camila_admin`) o `createsuperuser`.

### 2.7 Ejecución

```bash
python manage.py runserver
```

Abra `http://127.0.0.1:8000/` e inicie sesión con un usuario demo. El sistema detecta el rol de la cuenta y la lleva a su panel.

### 2.8 Pruebas automatizadas

```bash
python manage.py test                       # suite completa
python manage.py test apps.inventario       # solo un módulo
```

Las pruebas crean una base temporal propia y no modifican los datos de desarrollo.

---

## 3. Manual de usabilidad por rol

### 3.1 Usuarios demo

| Usuario | Clave | Rol | Panel inicial |
|---|---|---|---|
| `gerencia` | `Alpha2026!` | Administrador General | Dashboard (`/`) |
| `finanzas` | `Alpha2026!` | Administración / Finanzas | Panel de Finanzas (`/finanzas/`) |
| `bodega` | `Alpha2026!` | Bodega / Logística | Stock en tiempo real (`/inventario/stock/`) |
| `supervisor` | `Alpha2026!` | Supervisor de Obras | Mis obras (`/obras/`) |
| `tecnico` | `Alpha2026!` | Técnico | Hojas de servicio (`/obras/hojas-servicio/`) |
| `consulta` | `Alpha2026!` | Consulta / Auditoría lectura | Consultas (`/consulta/catalogo/`) |
| `auditor` | `Alpha2026!` | Auditor interno (solo lectura) | Consultas (`/consulta/catalogo/`) |
| `camila_admin` | `admin123` | Superusuario (creado por `poblar_obras`) | Dashboard (`/`) |
| `supervisor1` | `sup123` | Supervisor de Obras (creado por `poblar_obras`) | Mis obras (`/obras/`) |

> Cambie estas claves antes de usar el sistema con datos reales.

### 3.2 Inicio de sesión

1. Ingrese su **usuario o correo** y su **contraseña**. No hay que elegir rol: el sistema lo detecta según la cuenta.
2. Tras 3 intentos fallidos la cuenta se bloquea 30 segundos.
3. El menú lateral muestra **solo el panel de su rol**.
4. La sesión se cierra sola tras **10 minutos sin actividad**. Al minuto 9 aparece un aviso con cuenta regresiva y el botón **Seguir conectado**.

### 3.3 Administrador General (`gerencia`)

Panel **Gestión Estratégica y Control** y **Consultas Globales**.

1. **Dashboard:** indicadores de artículos, stock crítico, obras activas, movimientos del día y el **Indicador de Merma del Mes** (valor perdido en CLP, unidades y detalle).
2. **Auditoría y Kardex:** revise todos los movimientos y genere un **contra-asiento** cuando un movimiento deba revertirse (motivo obligatorio). Gerencia no mueve stock manualmente.
3. **Aprobar Inventarios:** firme un acta (bodega, obra o auditoría mensual) y revise las sesiones de inventario físico cerradas.
4. **Alertas de Stock:** artículos bajo el mínimo, reporte PDF de reposición y acceso a **Gestionar Restock**.
5. **Usuarios y Roles:** cree cuentas, cambie roles y bloquee o active usuarios.
6. **Bitácora de Cambios** y **Registro de Accesos:** quién cambió qué, cuándo y desde qué IP, más los inicios de sesión exitosos y fallidos.
7. **Consultas Globales:** catálogo, facturas y proveedores en modo lectura.

### 3.4 Administración / Finanzas (`finanzas`)

1. **Panel Finanzas:** saldo disponible, pagos, facturas y restocks pendientes de aprobar.
2. **Facturas Finanzas:** prepare facturas en **borrador**; no mueven stock hasta que Bodega las confirma.
3. **Pagos a Proveedores:** registre pagos pendientes o realizados. Solo Finanzas ve completos los números de cuenta bancaria; los demás roles los ven enmascarados.
4. **Presupuestos de Obras:** cree obras con su presupuesto, tipo de servicio, N° de presupuesto, responsable, tarifa hora y margen esperado, y revise el cuadro de rentabilidad de cada una.
5. **Proveedores y Mandantes:** cree y edite fichas con región, comuna, ciudad, representante legal, contactos y cuentas.
6. **Restock de Bodega:** apruebe o rechace (con motivo) las órdenes de reposición.
7. **Catálogo** y **Kardex:** consulta de artículos y movimientos.

### 3.5 Bodega / Logística (`bodega`)

1. **Stock en Tiempo Real:** existencias, mínimos y críticos.
2. **Catálogo de Artículos:** cree y edite artículos y use **Nueva Categoría** para agregar categorías sin salir de la lista.
3. **Compras y Facturas:** registre documentos de entrada y confirme los borradores de Finanzas.
4. **Despachos a Obras:** atienda las solicitudes de los supervisores con firma digital del técnico, o recházelas con motivo.
5. **Mermas y Devoluciones:** registre mermas, devoluciones desde obra o a proveedor y uso interno, siempre con justificación.
6. **Inventario Físico:** por sector o con el **Checklist General de Bodega**.
7. **Restock de Bodega:** solicite reposición de artículos.
8. **Kardex (solo lectura)** y **Proveedores y Clientes:** consulta.

### 3.6 Supervisor de Obras (`supervisor`)

1. **Mis Obras Asignadas:** obras bajo su responsabilidad (y las que aún no tienen responsable) con su resultado financiero.
2. **Detalle de obra:** cuadro de rentabilidad, pedidos a Bodega con su estado real y cambio de estado de la obra. Una obra no se puede cerrar con pedidos pendientes.
3. **Solicitudes de Materiales:** pida materiales para una obra activa; la solicitud llega de inmediato a Bodega.
4. **Hojas de Servicio:** registre trabajos y **horas hombre**; las horas se valorizan como costo de mano de obra.
5. **Stock y Kardex (Lectura):** disponibilidad en bodega y movimientos asociados a las obras.

### 3.7 Técnico (`tecnico`)

1. **Hojas de Servicio:** registre el trabajo realizado y las horas invertidas.
2. **Stock y Kardex (Lectura):** disponibilidad y movimientos de obra.
3. **Restock de Bodega:** revise el material recibido de una orden aprobada, complete el checklist de conformidad y confirme el ingreso al stock.
4. **Checklist de Bodega:** consulta del conteo general (solo Bodega lo registra).

### 3.8 Consulta / Auditoría lectura (`consulta`, `auditor`)

1. **Consultas Globales:** catálogo, facturas y proveedores sin opciones de edición.
2. **Cardex Auditoría:** historial inmutable con filtros por artículo, tipo, fechas, usuario y documento, exportable a Excel y PDF.

---

## 4. Guía de flujos operativos

### 4.1 Ingreso de documentos con descuentos en cascada y PMP

*Rol: Bodega. Ruta: Compras y Facturas → Nuevo documento.*

1. Seleccione proveedor, tipo (Factura, Boleta, Guía de Despacho o Nota de Crédito), número y fecha.
2. Agregue las líneas: artículo, cantidad, precio base y hasta **tres descuentos sucesivos**. Cada descuento se aplica sobre el precio que dejó el anterior. Por ejemplo, $10.000 con 10%, 5% y 2% queda en $8.379.
3. La tabla muestra en vivo el **Total Neto**, el **IVA (19%)** y el **Total Bruto**.
4. Al confirmar, en una sola transacción:
   - Factura, boleta y guía **suman stock** y recalculan el **Precio Medio Ponderado**: PMP = (stock anterior × PMP anterior + cantidad × costo nuevo) / stock nuevo.
   - La nota de crédito **resta stock** y mantiene el PMP.
   - Cada línea deja su asiento en el Cardex. Si una línea falla, no se guarda nada.
5. Un folio repetido del mismo proveedor y tipo se rechaza.

### 4.2 Flujo de Restock en 3 pasos

*Ruta: Restock de Bodega (`/inventario/restock/`).*

1. **Bodega solicita:** artículo, proveedor opcional, cantidad y costo unitario estimado. Estado: *Pendiente Aprobación Finanzas*.
2. **Finanzas aprueba el presupuesto** (o lo rechaza indicando el motivo). Estado: *Presupuesto Aprobado*.
3. **Técnico o Bodega revisa el material** recibido: marca cantidad correcta, buen estado y especificación técnica, y confirma. El material entra al stock como ENTRADA en el Cardex y se actualizan el último costo y el PMP. Estado: *Insertada en Stock*.

Cada etapa registra quién actuó y cuándo.

### 4.3 Solicitud y despacho a obra con firma digital

1. **Supervisor:** en *Solicitudes de Materiales* elige la obra activa, el material, la cantidad y el sector.
2. **Bodega:** en *Despachos a Obras* revisa la solicitud; el sistema avisa si falta stock.
3. Selecciona al **técnico receptor**, que firma en pantalla, y confirma. Se emite el **vale de salida**, se descuenta el stock al PMP vigente y el costo se carga a la obra.
4. Si no se puede atender, Bodega **rechaza** con motivo; el supervisor ve el estado y el motivo en su panel.

### 4.4 Inventario físico por sector y checklist general

**Por sector** (*Inventario Físico → Inventario por Sector*):

1. Abra una sesión para un sector; solo puede haber una abierta por sector.
2. Ingrese el conteo real de cada artículo; puede guardar y continuar después.
3. Al cerrar, se calculan y valorizan las diferencias y se generan los ajustes (+/−) en el Cardex. Si hay diferencias, la observación es obligatoria. Una sesión cerrada no se reabre.

**Checklist general** (*pestaña Checklist General de Bodega*):

1. La tabla muestra todos los artículos activos, con buscador y filtro por categoría.
2. Marque **Revisado** en cada artículo y anote el stock contado. La diferencia y el estado (Cuadrado, Faltante o Sobrante) se calculan en vivo. **Marcar todos como verificados** marca los artículos visibles.
3. Al registrar, los artículos revisados quedan en una sesión cerrada y las diferencias se ajustan en el Cardex.

### 4.5 Evaluación financiera de proyectos

*Roles: Finanzas (Presupuestos de Obras), Gerencia y Supervisor (detalle de la obra).*

| Concepto | Cálculo |
|---|---|
| Presupuesto cliente | Monto definido por Finanzas |
| Costo de materiales | Despachos a la obra − devoluciones desde la obra (cantidad × costo de cada movimiento) |
| Costo de mano de obra | Costo fijo + horas de las hojas de servicio × tarifa hora |
| Costo total real | Materiales + mano de obra |
| Utilidad | Presupuesto − costo total real |
| Margen real (%) | Utilidad / presupuesto × 100 (se compara con el margen esperado) |

El indicador muestra **RENTABLE (+$…)** en verde o **EN PÉRDIDA / SOBRECOSTO (−$…)** en rojo.

### 4.6 Accesibilidad

En la barra superior (y arriba a la derecha en el login):

- **A- / A / A+:** tamaño de letra (14, 16 o 18,5 px).
- **Oscuro / Claro / Alto Contraste:** el alto contraste usa fondo negro, texto blanco y enlaces y bordes amarillos.
- **ES / EN:** idioma de la navegación, títulos y botones comunes.

Las preferencias se guardan en el navegador y se mantienen entre sesiones.

### 4.7 Auditoría y contra-asientos del Cardex inmutable

- Cada movimiento de inventario se copia automáticamente al **Cardex de Auditoría** con su tipo, cantidad, saldo resultante, usuario, obra y documento.
- Los registros **no se pueden editar ni eliminar**, ni uno a uno ni de forma masiva.
- Para corregir un error, Gerencia genera un **contra-asiento** desde *Auditoría y Kardex* indicando el motivo:
  - El contra-asiento revierte el efecto en el stock y no permite dejar saldo negativo.
  - Un movimiento solo se puede anular una vez.
  - El registro original y su reversa quedan enlazados.
- La **bitácora** guarda los valores anteriores y nuevos de cada cambio en artículos, entidades, obras y documentos, y el **registro de accesos** guarda los inicios de sesión exitosos y fallidos.
- El Cardex se puede exportar a **Excel** y **PDF**, y cada exportación queda registrada.

---

## 5. Estructura del proyecto

```
EVS3-proyecto--alpha/
├── apps/
│   ├── auditoria/    # Cardex inmutable, bitácora, accesos, exportaciones
│   ├── catalogo/     # Artículos y categorías
│   ├── core/         # Dashboard, alertas, actas, consultas
│   ├── entidades/    # Proveedores y mandantes
│   ├── finanzas/     # Pagos, facturas, presupuestos, restock
│   ├── inventario/   # Documentos, despachos, mermas, inventario físico, restock
│   │   └── services.py   # Reglas de negocio y punto único de escritura del stock
│   ├── obras/        # Obras, solicitudes, hojas de servicio, rentabilidad
│   └── usuarios/     # Login, roles (roles.py) y comando crear_roles
├── config/           # settings.py, urls.py, wsgi.py
├── static/           # CSS, JS e imágenes
├── templates/        # Plantilla base, login y vistas de inventario y catálogo
├── .env.example      # Variables de entorno de ejemplo
├── manage.py
└── requirements.txt
```
