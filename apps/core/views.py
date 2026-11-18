from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.apps import apps
from django.utils import timezone

from apps.catalogo.models import Articulo

# Detecta automáticamente el modelo de Kardex/Movimientos en la app inventario
def obtener_modelo_kardex():
    app_models = apps.get_app_config('inventario').get_models()
    for m in app_models:
        nombre = m.__name__.lower()
        if 'movimiento' in nombre or 'kardex' in nombre or 'cardex' in nombre:
            return m
    return None

ROLES_SISTEMA = [
    ('Administrador General', 'Administrador General / Gerencia'),
    ('Administrativo Finanzas', 'Administrador / Finanzas'),
    ('Bodega Logistica', 'Administrador de Bodega / Logística'),
    ('Supervisor de Obra', 'Supervisor de Obra'),
    ('Auditor', 'Auditor (Consultas)'),
]

@login_required
def dashboard(request):
    articulos = Articulo.objects.all()
    total_articulos = articulos.count()
    
    # Artículos con stock actual <= stock mínimo (HU-11)
    articulos_criticos = articulos.filter(stock_actual__lte=F('stock_minimo'))
    alertas_stock = articulos_criticos.count()
    
    ModeloKardex = obtener_modelo_kardex()
    if ModeloKardex:
        ultimos_movimientos = ModeloKardex.objects.select_related('articulo').order_by('-id')[:8]
        movimientos_hoy = ModeloKardex.objects.count()
    else:
        ultimos_movimientos = []
        movimientos_hoy = 0

    context = {
        'total_articulos': total_articulos,
        'alertas_stock': alertas_stock,
        'articulos_criticos': articulos_criticos[:5],
        'obras_activas': 4,
        'movimientos_hoy': movimientos_hoy,
        'ultimos_movimientos': ultimos_movimientos,
    }
    return render(request, 'core/dashboard.html', context)


# ==========================================
# 1. GESTIÓN DE USUARIOS Y ROLES (RBAC)
# ==========================================
@login_required
def gestion_usuarios(request):
    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        if accion == 'crear':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            password = request.POST.get('password', '')
            rol_nombre = request.POST.get('rol', '')

            if User.objects.filter(username=username).exists():
                messages.error(request, f'El nombre de usuario "{username}" ya está registrado.')
            else:
                user = User.objects.create_user(
                    username=username, email=email, password=password,
                    first_name=first_name, last_name=last_name
                )
                if rol_nombre:
                    grupo, _ = Group.objects.get_or_create(name=rol_nombre)
                    user.groups.add(grupo)
                messages.success(request, f'Empleado {username} registrado con rol {rol_nombre}.')
            return redirect('core:gestion_usuarios')

        elif accion == 'cambiar_rol':
            user_id = request.POST.get('user_id')
            nuevo_rol = request.POST.get('rol')
            u = get_object_or_404(User, pk=user_id)
            u.groups.clear()
            if nuevo_rol:
                grupo, _ = Group.objects.get_or_create(name=nuevo_rol)
                u.groups.add(grupo)
            messages.success(request, f'Rol de {u.username} actualizado a {nuevo_rol}.')
            return redirect('core:gestion_usuarios')

        elif accion == 'toggle_estado':
            user_id = request.POST.get('user_id')
            u = get_object_or_404(User, pk=user_id)
            if u != request.user:
                u.is_active = not u.is_active
                u.save()
                estado_txt = "activado" if u.is_active else "bloqueado"
                messages.info(request, f'Usuario {u.username} {estado_txt}.')
            else:
                messages.warning(request, 'No puedes desactivar tu propia cuenta.')
            return redirect('core:gestion_usuarios')

    usuarios = User.objects.prefetch_related('groups').all().order_by('-date_joined')
    return render(request, 'core/gestion_usuarios.html', {
        'usuarios': usuarios,
        'roles': ROLES_SISTEMA
    })


# ==========================================
# 2. PANEL DE ALERTAS DE STOCK (HU-11)
# ==========================================
@login_required
def panel_alertas_stock(request):
    categoria_q = request.GET.get('categoria', '')
    articulos_alerta = Articulo.objects.filter(stock_actual__lte=F('stock_minimo'))
    
    if categoria_q:
        articulos_alerta = articulos_alerta.filter(categoria__icontains=categoria_q)

    return render(request, 'core/alertas_stock.html', {
        'articulos_alerta': articulos_alerta,
        'categoria_q': categoria_q
    })


# ==========================================
# 3. AUDITORÍA KARDEX Y CONTRA-ASIENTO (HU-12)
# ==========================================
@login_required
def auditoria_kardex(request):
    q = request.GET.get('q', '').strip()
    ModeloKardex = obtener_modelo_kardex()
    
    if ModeloKardex:
        movimientos = ModeloKardex.objects.select_related('articulo').all().order_by('-id')
        if q:
            movimientos = movimientos.filter(articulo__nombre__icontains=q)
    else:
        movimientos = []

    return render(request, 'core/auditoria_kardex.html', {
        'movimientos': movimientos,
        'q': q
    })


@login_required
@transaction.atomic
def anular_movimiento_kardex(request, mov_id):
    ModeloKardex = obtener_modelo_kardex()
    if not ModeloKardex:
        messages.error(request, 'Modelo de Kardex no encontrado.')
        return redirect('core:auditoria_kardex')

    mov_original = get_object_or_404(ModeloKardex, pk=mov_id)
    
    if request.method == 'POST':
        motivo = request.POST.get('motivo', '').strip()
        if not motivo:
            messages.error(request, 'El motivo de ajuste es obligatorio para generar un contra-asiento.')
            return redirect('core:auditoria_kardex')

        articulo = mov_original.articulo
        cantidad = mov_original.cantidad
        tipo_orig = str(getattr(mov_original, 'tipo_movimiento', getattr(mov_original, 'tipo', ''))).upper()

        if 'ENTRADA' in tipo_orig or 'INGRESO' in tipo_orig:
            articulo.stock_actual -= cantidad
            tipo_reversa = 'CONTRA_ASIENTO_INGRESO'
        else:
            articulo.stock_actual += cantidad
            tipo_reversa = 'CONTRA_ASIENTO_EGRESO'
        articulo.save()

        ahora_str = timezone.now().strftime('%d/%m/%Y %H:%M')
        bitacora_detalle = f"ANULADO ID#{mov_original.id} | Por: {request.user.username} | Fecha: {ahora_str} | Motivo: {motivo}"

        nuevo_mov = ModeloKardex()
        nuevo_mov.articulo = articulo
        nuevo_mov.cantidad = cantidad
        if hasattr(nuevo_mov, 'tipo_movimiento'):
            nuevo_mov.tipo_movimiento = tipo_reversa
        elif hasattr(nuevo_mov, 'tipo'):
            nuevo_mov.tipo = tipo_reversa
            
        if hasattr(nuevo_mov, 'documento'):
            nuevo_mov.documento = bitacora_detalle
        elif hasattr(nuevo_mov, 'referencia'):
            nuevo_mov.referencia = bitacora_detalle
            
        if hasattr(nuevo_mov, 'usuario'):
            nuevo_mov.usuario = request.user
        nuevo_mov.save()

        messages.success(
            request, 
            f'Contra-asiento #{nuevo_mov.id} registrado en bitácora ({bitacora_detalle}).'
        )
        return redirect('core:auditoria_kardex')

    return redirect('core:auditoria_kardex')


# ==========================================
# 4. APROBACIÓN DE INVENTARIOS FÍSICOS Y DE OBRA
# ==========================================
@login_required
def aprobacion_inventarios(request):
    articulos = Articulo.objects.all()
    if request.method == 'POST':
        tipo_acta = request.POST.get('tipo_acta', 'Inventario Físico General')
        observacion = request.POST.get('observacion', 'Aprobado conforme por Gerencia.')
        ahora = timezone.now().strftime('%d/%m/%Y %H:%M')
        messages.success(
            request,
            f'Acta de "{tipo_acta}" APROBADA oficialmente por {request.user.username} el {ahora}. ({observacion})'
        )
        return redirect('core:aprobacion_inventarios')

    return render(request, 'core/aprobacion_inventarios.html', {
        'articulos': articulos,
    })


# ==========================================
# 5. CONSULTAS GLOBALES DE SOLO LECTURA
# ==========================================
@login_required
def consulta_lectura(request, seccion):
    registros = []
    titulo_seccion = "Consulta General"

    if seccion == 'catalogo':
        titulo_seccion = "Catálogo Maestro de Artículos"
        registros = Articulo.objects.all()
    elif seccion == 'facturas':
        titulo_seccion = "Documentos Tributarios y Facturas"
        for m in apps.get_app_config('inventario').get_models():
            if 'documento' in m.__name__.lower() and 'detalle' not in m.__name__.lower():
                registros = m.objects.all().order_by('-id')
                break
    elif seccion == 'entidades':
        titulo_seccion = "Directorio de Proveedores y Mandantes"
        for m in apps.get_app_config('entidades').get_models():
            if 'entidad' in m.__name__.lower() or 'proveedor' in m.__name__.lower():
                registros = m.objects.all()
                break

    return render(request, 'core/consulta_lectura.html', {
        'seccion': seccion,
        'titulo_seccion': titulo_seccion,
        'registros': registros,
    })

import os
from django.conf import settings
from django.http import HttpResponse
from fpdf import FPDF

@login_required
def exportar_pdf_gerencia(request, tipo_reporte):
    # 1. Crear documento PDF tamaño Carta
    pdf = FPDF(orientation='P', unit='mm', format='Letter')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # 2. Esquina Superior Izquierda: Logo de la Empresa
    ruta_logo = os.path.join(settings.BASE_DIR, 'static', 'img', 'logo_fyag.png')
    if os.path.exists(ruta_logo):
        pdf.image(ruta_logo, x=12, y=10, w=26)

    # Datos de la empresa junto al logo
    pdf.set_xy(42, 12)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(90, 6, 'FRIO Y AGROINDUSTRIA SPA', ln=1)
    pdf.set_x(42)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(90, 5, 'Ingenieria en Refrigeracion, Agroindustria y Logistica', ln=1)
    pdf.set_x(42)
    pdf.cell(90, 5, 'Casa Matriz - Chillan, Region de Nuble', ln=1)

    # 3. Esquina Superior Derecha: Recuadro tipo Factura (Fecha, Hora y Administrador)
    ahora = timezone.localtime(timezone.now())
    admin_nombre = request.user.get_full_name() or request.user.username

    # Dibuja el rectángulo del recuadro de factura (x=135, y=10, ancho=70, alto=28)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.4)
    pdf.rect(135, 10, 70, 28)

    pdf.set_xy(137, 12)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(66, 5, 'ORDEN / REPORTE DE GERENCIA', border='B', ln=1, align='C')

    pdf.set_x(137)
    pdf.set_font('Helvetica', '', 8.5)
    pdf.cell(66, 5, f'Fecha Emision: {ahora.strftime("%d/%m/%Y")}', ln=1)
    pdf.set_x(137)
    pdf.cell(66, 5, f'Hora Emision:  {ahora.strftime("%H:%M:%S")} hrs', ln=1)
    pdf.set_x(137)
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.cell(66, 5, f'Autorizado por: {admin_nombre[:22]}', ln=1)
    pdf.set_x(137)
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(66, 4, 'Cargo: Administrador General', ln=1)

    # Línea separadora inferior del membrete
    pdf.ln(10)
    pdf.set_y(44)
    pdf.line(12, 44, 205, 44)
    pdf.ln(6)

    # 4. Cuerpo Central: Tabla estilo Factura según el reporte solicitado
    if tipo_reporte == 'alertas':
        # Título de la tabla
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 8, 'DETALLE DE INSUMOS EN ESTADO DE ALERTA (ORDEN DE REPOSICION)', ln=1, align='C')
        pdf.ln(2)

        # Encabezados de la tabla
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(32, 8, 'CODIGO', border=1, align='C', fill=True)
        pdf.cell(85, 8, 'INSUMO / MATERIAL', border=1, align='L', fill=True)
        pdf.cell(25, 8, 'STOCK ACT.', border=1, align='C', fill=True)
        pdf.cell(25, 8, 'STOCK MIN.', border=1, align='C', fill=True)
        pdf.cell(26, 8, 'ESTADO', border=1, align='C', fill=True, ln=1)

        # Filas de datos desde PostgreSQL
        articulos = Articulo.objects.filter(stock_actual__lte=F('stock_minimo'))
        pdf.set_font('Helvetica', '', 9)
        if articulos.exists():
            for art in articulos:
                estado = 'QUIEBRE (0)' if art.stock_actual == 0 else 'BAJO MINIMO'
                codigo = str(getattr(art, 'codigo_interno', art.id))[:15]
                nombre = str(art.nombre)[:42]
                pdf.cell(32, 7, codigo, border=1, align='C')
                pdf.cell(85, 7, f' {nombre}', border=1, align='L')
                pdf.cell(25, 7, str(art.stock_actual), border=1, align='C')
                pdf.cell(25, 7, str(art.stock_minimo), border=1, align='C')
                pdf.cell(26, 7, estado, border=1, align='C', ln=1)
        else:
            pdf.cell(193, 10, 'Todos los insumos superan el stock minimo configurado.', border=1, align='C', ln=1)

        nombre_archivo = f"Orden_Reposicion_FYAG_{ahora.strftime('%d%m%Y')}.pdf"

    else:
        # Reporte de Auditoría Kardex
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 8, 'AUDITORIA INTEGRAL DEL KARDEX Y CONTRA-ASIENTOS', ln=1, align='C')
        pdf.ln(2)

        # Encabezados de la tabla
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font('Helvetica', 'B', 8.5)
        pdf.cell(16, 8, 'ID', border=1, align='C', fill=True)
        pdf.cell(52, 8, 'PRODUCTO', border=1, align='L', fill=True)
        pdf.cell(38, 8, 'OPERACION', border=1, align='C', fill=True)
        pdf.cell(18, 8, 'CANT.', border=1, align='C', fill=True)
        pdf.cell(69, 8, 'REFERENCIA / BITACORA', border=1, align='L', fill=True, ln=1)

        ModeloKardex = obtener_modelo_kardex()
        movimientos = ModeloKardex.objects.select_related('articulo').all().order_by('-id')[:50] if ModeloKardex else []

        pdf.set_font('Helvetica', '', 8)
        if movimientos:
            for mov in movimientos:
                tipo_op = str(getattr(mov, 'tipo_movimiento', getattr(mov, 'tipo', 'MOV')))[:20]
                ref = str(getattr(mov, 'documento', getattr(mov, 'referencia', '-')))[:38]
                prod = str(mov.articulo)[:26]
                pdf.cell(16, 7, f'#{mov.id}', border=1, align='C')
                pdf.cell(52, 7, f' {prod}', border=1, align='L')
                pdf.cell(38, 7, tipo_op, border=1, align='C')
                pdf.cell(18, 7, str(mov.cantidad), border=1, align='C')
                pdf.cell(69, 7, f' {ref}', border=1, align='L', ln=1)
        else:
            pdf.cell(193, 10, 'Sin movimientos registrados en el Kardex.', border=1, align='C', ln=1)

        nombre_archivo = f"Auditoria_Kardex_FYAG_{ahora.strftime('%d%m%Y')}.pdf"

    # 5. Entregar el PDF generado al navegador
    pdf_bytes = bytes(pdf.output())
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{nombre_archivo}"'
    return response