#Implementa la lógica atómica de anulación que valida el motivo, revierte el stock del artículo y registra la transacción inalterable en PostgreSQL (además del envío opcional del log de auditoría).
import datetime
from io import BytesIO
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied

import openpyxl
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from apps.catalogo.models import Articulo
from .models import MovimientoCardex, BitacoraAuditoria, LogAcceso
from .forms import AnulacionControladaForm, FiltroCardexForm
from .middleware import get_current_ip


# --- FUNCIONES DE VERIFICACIÓN DE ROLES ---

def usuario_puede_auditar(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    roles_permitidos = {'ADMINISTRADOR_GENERAL', 'AUDITOR', 'CONSULTA', 'FINANZAS'}
    grupos_usuario = {g.name.upper() for g in user.groups.all()}
    rol_attr = getattr(user, 'rol', '').upper()
    return bool(grupos_usuario & roles_permitidos) or (rol_attr in roles_permitidos)


def usuario_es_admin_general(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    grupos_usuario = {g.name.upper() for g in user.groups.all()}
    rol_attr = getattr(user, 'rol', '').upper()
    return ('ADMINISTRADOR_GENERAL' in grupos_usuario) or (rol_attr == 'ADMINISTRADOR_GENERAL')


class PuedeAuditarMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return usuario_puede_auditar(self.request.user)


class SoloAdminGeneralMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return usuario_es_admin_general(self.request.user)


# --- VISTAS PRINCIPALES ---

def _filtrar_cardex(request):
    qs = MovimientoCardex.objects.select_related('articulo', 'usuario', 'contra_asiento').all()

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
        context['form_anulacion'] = AnulacionControladaForm()
        context['es_admin_general'] = usuario_es_admin_general(self.request.user)
        return context


class AnularMovimientoView(SoloAdminGeneralMixin, View):
    def post(self, request, *args, **kwargs):
        form = AnulacionControladaForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Debe ingresar un motivo válido de al menos 10 caracteres para anular.")
            return redirect('auditoria:lista_cardex')

        mov_id = form.cleaned_data['movimiento_id']
        motivo = form.cleaned_data['motivo_anulacion']

        with transaction.atomic():
            mov_original = get_object_or_404(MovimientoCardex.objects.select_for_update(), pk=mov_id)

            if mov_original.es_reversa or hasattr(mov_original, 'contra_asiento') and mov_original.contra_asiento is not None:
                messages.warning(request, f"El asiento #{mov_original.id} ya fue reversado anteriormente.")
                return redirect('auditoria:lista_cardex')

            articulo = Articulo.objects.select_for_update().get(pk=mov_original.articulo_id)
            cantidad_inversa = -mov_original.cantidad
            nuevo_stock = articulo.stock_actual + cantidad_inversa

            if nuevo_stock < 0:
                messages.error(request, f"No se puede anular: el stock de '{articulo.nombre}' quedaría negativo ({nuevo_stock}).")
                return redirect('auditoria:lista_cardex')

            articulo.stock_actual = nuevo_stock
            articulo.save(update_fields=['stock_actual'])

            contra_asiento = MovimientoCardex.objects.create(
                articulo=articulo,
                tipo_movimiento='ANULACION',
                cantidad=cantidad_inversa,
                saldo_resultante=nuevo_stock,
                valor_unitario=mov_original.valor_unitario,
                usuario=request.user,
                obra_referencia=mov_original.obra_referencia,
                documento_referencia=mov_original.documento_referencia,
                justificacion=f"ANULACIÓN ASIENTO #{mov_original.id}: {motivo}",
                es_reversa=True
            )

            # Vincular contra-asiento de forma controlada sin alterar datos históricos
            MovimientoCardex.objects.filter(pk=mov_original.pk).update(contra_asiento=contra_asiento)

            BitacoraAuditoria.objects.create(
                usuario=request.user,
                ip_origen=get_current_ip(),
                modulo='Auditoria',
                accion='ANULAR',
                objeto_id=str(mov_original.id),
                descripcion=f"Contra-asiento #{contra_asiento.id} generado sobre movimiento #{mov_original.id} ({articulo.nombre}). Motivo: {motivo}"
            )

        messages.success(request, f"Contra-asiento #{contra_asiento.id} generado correctamente. Stock actualizado a {nuevo_stock}.")
        return redirect('auditoria:lista_cardex')


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


def usuario_es_admin_general(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    grupos_usuario = {g.name.upper() for g in user.groups.all()}
    rol_attr = getattr(user, 'rol', '').upper()
    return bool(grupos_usuario & {'ADMINISTRADOR_GENERAL', 'GERENCIA'}) or (rol_attr in {'ADMINISTRADOR_GENERAL', 'GERENCIA'})