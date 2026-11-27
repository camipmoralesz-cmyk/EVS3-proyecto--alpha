#Implementa la lógica atómica de anulación que valida el motivo, revierte el stock del artículo y registra la transacción inalterable en PostgreSQL (además del envío opcional del log de auditoría).
import datetime
from io import BytesIO
from django.shortcuts import redirect
from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse

import openpyxl
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from apps.catalogo.models import Articulo
from apps.usuarios.roles import tiene_rol
from .models import MovimientoCardex, BitacoraAuditoria, LogAcceso
from .forms import FiltroCardexForm
from .middleware import get_current_ip


# --- FUNCIONES DE VERIFICACIÓN DE ROLES ---

def usuario_puede_auditar(user):
    return tiene_rol(user, 'gerencia', 'consulta', 'finanzas', 'auditor')


def usuario_es_admin_general(user):
    return tiene_rol(user, 'gerencia')


class PuedeAuditarMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return usuario_puede_auditar(self.request.user)


class SoloAdminGeneralMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return usuario_es_admin_general(self.request.user)


# --- VISTAS PRINCIPALES ---

def _filtrar_cardex(request):
    qs = MovimientoCardex.objects.select_related('articulo', 'usuario', 'obra', 'contra_asiento').all()

    articulo_id = request.GET.get('articulo')
    tipo = request.GET.get('tipo_movimiento')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    usuario = request.GET.get('usuario')
    documento = request.GET.get('documento')

    if articulo_id:
        qs = qs.filter(articulo_id=articulo_id)
    if tipo:
        qs = qs.filter(tipo_movimiento=tipo)
    if fecha_inicio:
        qs = qs.filter(fecha_hora__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha_hora__date__lte=fecha_fin)
    if usuario:
        qs = qs.filter(usuario__username__icontains=usuario.strip())
    if documento:
        doc = documento.strip()
        qs = qs.filter(
            Q(documento_referencia__icontains=doc) |
            Q(obra_referencia__icontains=doc)
        )
    return qs


class CardexListView(PuedeAuditarMixin, ListView):
    model = MovimientoCardex
    template_name = 'auditoria/cardex_list.html'
    context_object_name = 'movimientos'
    paginate_by = 50

    def get_queryset(self):
        return _filtrar_cardex(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['articulos'] = Articulo.objects.all().order_by('nombre')
        context['articulo_seleccionado'] = self.request.GET.get('articulo', '')
        context['form_filtros'] = FiltroCardexForm(self.request.GET)
        return context


class AnularMovimientoView(SoloAdminGeneralMixin, View):
    """El Cardex de Auditoría es de solo lectura para todos los perfiles. Las anulaciones
    se hacen solo desde el Kardex de Gerencia (core:anular_movimiento), que usa
    anular_movimiento_inventario() y deja el contra-asiento reflejado en este Cardex.
    Se conserva la URL: los demás perfiles siguen recibiendo 403 y Gerencia es redirigida."""

    def post(self, request, *args, **kwargs):
        messages.info(request, "El Cardex de Auditoría es de solo lectura. Las anulaciones se registran "
                               "desde el Kardex de Gerencia.")
        return redirect('core:auditoria_kardex')


class BitacoraAuditoriaListView(PuedeAuditarMixin, ListView):
    model = BitacoraAuditoria
    template_name = 'auditoria/bitacora_list.html'
    context_object_name = 'registros'
    paginate_by = 50

    def get_queryset(self):
        qs = BitacoraAuditoria.objects.select_related('usuario').all()
        modulo = self.request.GET.get('modulo', '').strip()
        accion = self.request.GET.get('accion', '').strip()
        if modulo:
            qs = qs.filter(modulo__icontains=modulo)
        if accion:
            qs = qs.filter(accion=accion)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['modulo_filtro'] = self.request.GET.get('modulo', '')
        context['accion_filtro'] = self.request.GET.get('accion', '')
        return context


class LogsAccesoListView(PuedeAuditarMixin, ListView):
    model = LogAcceso
    template_name = 'auditoria/logs_acceso.html'
    context_object_name = 'logs'
    paginate_by = 50


# --- EXPORTACIÓN A EXCEL Y PDF ---

@login_required
@user_passes_test(usuario_puede_auditar)
def exportar_cardex_excel(request):
    movimientos = _filtrar_cardex(request)

    BitacoraAuditoria.objects.create(
        usuario=request.user,
        ip_origen=get_current_ip(),
        modulo='Auditoria',
        accion='EXPORTAR',
        modelo_afectado='MovimientoCardex',
        objeto_id='EXPORT_XLSX',
        descripcion=f"Exportación Excel del Cardex ({movimientos.count()} registros)"
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cardex Auditoria"

    headers = ["ID", "Fecha y Hora", "Artículo", "Tipo", "Cantidad", "Saldo", "Usuario", "Documento", "Justificación"]
    ws.append(headers)

    for m in movimientos:
        ws.append([
            m.id,
            m.fecha_hora.strftime("%d/%m/%Y %H:%M"),
            m.articulo.nombre,
            m.get_tipo_movimiento_display(),
            m.cantidad,
            m.saldo_resultante,
            m.usuario.username if m.usuario else "Sistema",
            m.documento_referencia or "-",
            m.justificacion
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    fecha_str = datetime.date.today().strftime("%Y%m%d")
    response["Content-Disposition"] = f'attachment; filename="cardex_auditoria_{fecha_str}.xlsx"'
    wb.save(response)
    return response


@login_required
@user_passes_test(usuario_puede_auditar)
def exportar_cardex_pdf(request):
    movimientos = _filtrar_cardex(request)[:300]

    BitacoraAuditoria.objects.create(
        usuario=request.user,
        ip_origen=get_current_ip(),
        modulo='Auditoria',
        accion='EXPORTAR',
        modelo_afectado='MovimientoCardex',
        objeto_id='EXPORT_PDF',
        descripcion=f"Exportación PDF del Cardex ({len(movimientos)} registros)"
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    styles = getSampleStyleSheet()
    elementos = [
        Paragraph(f"Reporte Oficial de Auditoría - Cardex Inmutable ({datetime.datetime.now().strftime('%d/%m/%Y %H:%M')})", styles['Title'])
    ]

    data = [["ID", "Fecha", "Artículo", "Tipo", "Cant.", "Saldo", "Usuario", "Documento"]]
    for m in movimientos:
        data.append([
            str(m.id),
            m.fecha_hora.strftime("%d/%m/%Y %H:%M"),
            m.articulo.nombre[:30],
            m.get_tipo_movimiento_display()[:18],
            str(m.cantidad),
            str(m.saldo_resultante),
            m.usuario.username if m.usuario else "Sistema",
            (m.documento_referencia or "-")[:20]
        ])

    tabla = Table(data, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    elementos.append(tabla)
    doc.build(elementos)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    fecha_str = datetime.date.today().strftime("%Y%m%d")
    response['Content-Disposition'] = f'attachment; filename="cardex_auditoria_{fecha_str}.pdf"'
    return response