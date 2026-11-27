from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db.models import F
from django.apps import apps
from django.utils import timezone

from apps.catalogo.models import Articulo
from apps.inventario.models import DocumentoEntrada, MovimientoInventario, SesionInventario, SolicitudDespacho
from apps.inventario.services import MIN_JUSTIFICACION, AnulacionError, anular_movimiento_inventario
from apps.obras.models import Obra
from apps.usuarios.roles import rol_requerido

from .models import ActaAprobacionInventario

# Mantiene compatibilidad retornando directamente el modelo Kardex de inventario
def obtener_modelo_kardex():
    return MovimientoInventario

ROLES_SISTEMA = [
    ('Administrador General', 'Administrador General / Gerencia'),
    ('Administración', 'Administración / Finanzas'),
    ('Bodega / Logística', 'Bodega / Logística'),
    ('Supervisor de Obras', 'Supervisor de Obras'),
    ('Técnico', 'Técnico en Terreno'),
    ('Consulta', 'Consulta / Auditoría (Solo Lectura)'),
    ('Auditor', 'Auditor Interno / Fiscalización'),
]

@rol_requerido('gerencia', 'bodega', 'finanzas', 'supervisor')
def dashboard(request):
    hoy = timezone.localdate()
    articulos = Articulo.objects.filter(activo=True)
    total_articulos = articulos.count()

    # Artículos con stock actual <= stock mínimo (HU-11)
    articulos_criticos = articulos.filter(stock_actual__lte=F('stock_minimo')).order_by('stock_actual')
    alertas_stock = articulos_criticos.count()

    ultimos_movimientos = (
        MovimientoInventario.objects
        .select_related('articulo', 'usuario', 'documento')
        .order_by('-fecha', '-id')[:8]
    )
    # Solo movimientos de stock (los accesos al sistema no tienen artículo)
    movimientos_hoy = MovimientoInventario.objects.filter(
        fecha__date=hoy, articulo__isnull=False
    ).count()

    obras_activas = Obra.objects.filter(estado=Obra.Estado.ACTIVA).count()
    solicitudes_pendientes = SolicitudDespacho.objects.filter(
        estado=SolicitudDespacho.Estado.PENDIENTE
    ).count()
    facturas_borrador = DocumentoEntrada.objects.filter(
        estado=DocumentoEntrada.ESTADO_BORRADOR
    ).count()
    # Indicador de merma del mes: eventos, unidades y pérdida económica (al costo del asiento)
    mermas_qs = list(
        MovimientoInventario.objects
        .filter(tipo_movimiento=MovimientoInventario.TIPO_MERMA, fecha__year=hoy.year, fecha__month=hoy.month)
        .select_related('articulo', 'obra', 'usuario')
        .order_by('-fecha', '-id')
    )
    mermas_mes = len(mermas_qs)
    mermas_unidades_mes = sum((m.cantidad for m in mermas_qs), Decimal('0'))
    mermas_valor_mes = sum(int(m.cantidad * m.costo_unitario) for m in mermas_qs)
    ultimas_mermas = [
        {
            'fecha': m.fecha,
            'articulo': m.articulo,
            'obra': m.obra,
            'cantidad': m.cantidad,
            'valor': int(m.cantidad * m.costo_unitario),
            'usuario': m.usuario,
            'justificacion': m.justificacion,
        }
        for m in mermas_qs[:5]
    ]

    context = {
        'total_articulos': total_articulos,
        'alertas_stock': alertas_stock,
        'articulos_criticos': articulos_criticos[:5],
        'articulos_alerta': articulos_criticos[:6],
        'obras_activas': obras_activas,
        'movimientos_hoy': movimientos_hoy,
        'ultimos_movimientos': ultimos_movimientos,
        'solicitudes_pendientes': solicitudes_pendientes,
        'facturas_borrador': facturas_borrador,
        'mermas_mes': mermas_mes,
        'mermas_unidades_mes': mermas_unidades_mes,
        'mermas_valor_mes': mermas_valor_mes,
        'ultimas_mermas': ultimas_mermas,
    }
    return render(request, 'core/dashboard.html', context)


# ==========================================
# 1. GESTIÓN DE USUARIOS Y ROLES (RBAC)
# ==========================================
@rol_requerido('gerencia')
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
                try:
                    usuario_temporal = User(
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name
                    )

                    validate_password(password, user=usuario_temporal)

                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name
                    )

                    if rol_nombre:
                        grupo, _ = Group.objects.get_or_create(name=rol_nombre)
                        user.groups.add(grupo)

                    messages.success(
                        request,
                        f'Empleado {username} registrado con rol {rol_nombre}.'
                    )

                except ValidationError as error:
                    for mensaje in error.messages:
                        messages.error(request, mensaje)

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
@rol_requerido('gerencia', 'bodega', 'finanzas')
def panel_alertas_stock(request):
    categoria_q = request.GET.get('categoria', '')
    articulos_alerta = Articulo.objects.filter(stock_actual__lte=F('stock_minimo'))
    
    if categoria_q:
        articulos_alerta = articulos_alerta.filter(categoria__nombre__icontains=categoria_q)

    return render(request, 'core/alertas_stock.html', {
        'articulos_alerta': articulos_alerta,
        'categoria_q': categoria_q
    })


# ==========================================
# 3. AUDITORÍA KARDEX Y CONTRA-ASIENTO (HU-12)
# ==========================================
def auditoria_kardex(request, *args, **kwargs):
    """Pantalla única del Kardex (la misma de /auditoria/cardex/): filtros, exportaciones y,
    solo para Gerencia, el contra-asiento. Los permisos los aplica la vista de auditoría."""
    from apps.auditoria.views import CardexListView
    return CardexListView.as_view()(request, *args, **kwargs)


@rol_requerido('gerencia')
def anular_movimiento_kardex(request, mov_id):
    """Contra-asiento desde el Kardex. La lógica vive en anular_movimiento_inventario(),
    la misma que usa el Cardex de Auditoría."""
    mov = get_object_or_404(MovimientoInventario.objects.select_related('articulo'), pk=mov_id)
    if request.method != 'POST':
        return redirect('core:auditoria_kardex')

    motivo = request.POST.get('motivo', '').strip()
    if len(motivo) < MIN_JUSTIFICACION:
        messages.error(request, f'Debe ingresar un motivo de al menos {MIN_JUSTIFICACION} caracteres para generar un contra-asiento.')
        return redirect('core:auditoria_kardex')

    try:
        contra = anular_movimiento_inventario(mov_id, request.user, motivo)
    except AnulacionError as e:
        avisos = {
            'sin_articulo': 'Los registros de ingreso/salida de personal son inmutables y no requieren contra-asiento de stock.',
            'es_anulacion': 'Este registro ya corresponde a un contra-asiento de anulación.',
            'ya_anulado': f'El movimiento #{mov_id} ya fue anulado anteriormente.',
        }
        if e.codigo in avisos:
            messages.warning(request, avisos[e.codigo])
        elif e.codigo == 'stock_negativo':
            messages.error(
                request,
                f'No se puede anular el movimiento #{mov_id}: el stock de "{mov.articulo.nombre}" quedaría negativo.'
            )
        else:
            messages.error(request, ' '.join(e.messages))
        return redirect('core:auditoria_kardex')

    messages.success(
        request,
        f'Contra-asiento #{contra.id} registrado en bitácora ({contra.referencia}). '
        f'Stock actualizado: {contra.stock_anterior} → {contra.stock_posterior}.'
    )
    return redirect('core:auditoria_kardex')


# ==========================================
# 4. APROBACIÓN DE INVENTARIOS FÍSICOS Y DE OBRA
# ==========================================
@rol_requerido('gerencia')
def aprobacion_inventarios(request):
    articulos = Articulo.objects.filter(activo=True).order_by('nombre')
    if request.method == 'POST':
        tipo_acta = request.POST.get('tipo_acta', '')
        observacion = request.POST.get('observacion', '').strip()
        if tipo_acta not in dict(ActaAprobacionInventario.TIPO_CHOICES):
            messages.error(request, 'Seleccione un tipo de revisión válido.')
            return redirect('core:aprobacion_inventarios')
        if not observacion:
            messages.error(request, 'Las observaciones de Gerencia son obligatorias para aprobar el acta.')
            return redirect('core:aprobacion_inventarios')

        acta = ActaAprobacionInventario.objects.create(
            tipo_acta=tipo_acta,
            observacion=observacion,
            total_articulos_visados=articulos.count(),
            articulos_criticos_detectados=articulos.filter(stock_actual__lte=F('stock_minimo')).count(),
            aprobado_por=request.user,
        )
        messages.success(
            request,
            f'Acta #{acta.pk} de "{acta.get_tipo_acta_display()}" aprobada por {request.user.username} '
            f'({acta.total_articulos_visados} artículos visados, {acta.articulos_criticos_detectados} críticos).'
        )
        return redirect('core:aprobacion_inventarios')

    return render(request, 'core/aprobacion_inventarios.html', {
        'articulos': articulos,
        'tipos_acta': ActaAprobacionInventario.TIPO_CHOICES,
        'actas_aprobadas': ActaAprobacionInventario.objects.select_related('aprobado_por').all()[:10],
        'sesiones_cerradas': SesionInventario.objects.filter(estado='CERRADA')
                                                    .select_related('abierta_por', 'cerrada_por')[:10],
    })


# ==========================================
# 5. CONSULTAS GLOBALES DE SOLO LECTURA
# ==========================================
@rol_requerido('gerencia', 'consulta')
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

@rol_requerido('gerencia')
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
        pdf.set_font('Helvetica', 'B', 8)
        pdf.cell(12, 8, 'ID', border=1, align='C', fill=True)
        pdf.cell(26, 8, 'PERSONAL', border=1, align='L', fill=True)
        pdf.cell(42, 8, 'PRODUCTO / RECURSO', border=1, align='L', fill=True)
        pdf.cell(38, 8, 'OPERACION', border=1, align='C', fill=True)
        pdf.cell(15, 8, 'CANT.', border=1, align='C', fill=True)
        pdf.cell(60, 8, 'MOTIVO / REFERENCIA', border=1, align='L', fill=True, ln=1)

        movimientos = (
            MovimientoInventario.objects
            .select_related('articulo', 'usuario')
            .all()
            .order_by('-fecha', '-id')[:50]
        )

        pdf.set_font('Helvetica', '', 7.5)
        if movimientos:
            for mov in movimientos:
                tipo_op = mov.get_tipo_movimiento_display()[:24]
                ref = str(mov.referencia or mov.documento or '-')[:36]
                prod = str(mov.articulo)[:24] if mov.articulo else 'Acceso Sistema'
                personal = (mov.usuario.username if mov.usuario else 'Sistema')[:15]
                cant_txt = str(mov.cantidad) if mov.articulo else '-'
                pdf.cell(12, 7, f'#{mov.id}', border=1, align='C')
                pdf.cell(26, 7, f' {personal}', border=1, align='L')
                pdf.cell(42, 7, f' {prod}', border=1, align='L')
                pdf.cell(38, 7, tipo_op, border=1, align='C')
                pdf.cell(15, 7, cant_txt, border=1, align='C')
                pdf.cell(60, 7, f' {ref}', border=1, align='L', ln=1)
        else:
            pdf.cell(193, 10, 'Sin movimientos registrados en el Kardex.', border=1, align='C', ln=1)

        nombre_archivo = f"Auditoria_Kardex_FYAG_{ahora.strftime('%d%m%Y')}.pdf"

    # 5. Entregar el PDF generado al navegador
    pdf_bytes = bytes(pdf.output())
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{nombre_archivo}"'
    return response
