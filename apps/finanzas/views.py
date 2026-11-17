from decimal import Decimal
import re

from django.contrib import messages
from django.db import connection, transaction
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Replace
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.entidades.forms import ContactoFormSet, CuentaFormSet, ProveedorForm
from apps.entidades.models import Proveedor
from apps.inventario.models import DocumentoEntrada
from apps.obras.models import Obra
from apps.usuarios.roles import rol_requerido

from .forms import ObservacionFacturaForm, PagoProveedorForm, PresupuestoObraForm
from .models import PagoProveedor, SaldoInicialEmpresa


def _obra_tiene_movimientos(obra):
    """
    Verifica de forma segura si la obra tiene movimientos en MovimientoCardex
    (incluso si la tabla de auditoría aún no ha sido migrada).
    """
    tablas = connection.introspection.table_names()
    if 'auditoria_movimientocardex' not in tablas:
        return False
    from apps.auditoria.models import MovimientoCardex
    return MovimientoCardex.objects.filter(obra=obra).exists()


@rol_requerido('finanzas')
def panel_finanzas(request):
    """Muestra el saldo inicial menos los pagos efectivamente realizados."""
    saldo_inicial = SaldoInicialEmpresa.objects.get(pk=1)
    pagos_efectuados = PagoProveedor.objects.filter(
        estado=PagoProveedor.Estado.PAGADO,
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    saldo_disponible = saldo_inicial.monto - pagos_efectuados

    return render(request, 'finanzas/panel.html', {
        'titulo': 'Panel de Finanzas',
        'saldo_inicial': saldo_inicial.monto,
        'pagos_efectuados': pagos_efectuados,
        'saldo_disponible': saldo_disponible,
    })


@rol_requerido('finanzas')
@require_GET
def lista_facturas_finanzas(request):
    """Muestra documentos de entrada para consulta y valorización, sin edición."""
    q = request.GET.get('q', '').strip()
    documentos = DocumentoEntrada.objects.select_related(
        'proveedor',
        'registrado_por',
    ).prefetch_related('detalles__articulo')

    if q:
        documentos = documentos.filter(
            Q(numero_documento__icontains=q)
            | Q(proveedor__razon_social__icontains=q)
            | Q(proveedor__rut__icontains=q)
        )

    return render(request, 'finanzas/facturas_lista.html', {
        'titulo': 'Facturas y Documentos Ingresados',
        'documentos': documentos,
        'q': q,
    })


@rol_requerido('finanzas')
@require_http_methods(['GET', 'POST'])
def detalle_factura_finanzas(request, pk):
    """Consulta una factura y permite crear un reporte sin modificarla."""
    documento = get_object_or_404(
        DocumentoEntrada.objects.select_related('proveedor', 'registrado_por'),
        pk=pk,
    )
    detalles = documento.detalles.select_related('articulo').all()
    if request.method == 'POST':
        formulario_observacion = ObservacionFacturaForm(request.POST)
        if formulario_observacion.is_valid():
            observacion = formulario_observacion.save(commit=False)
            observacion.documento = documento
            observacion.usuario = request.user
            observacion.save()
            messages.success(request, 'El reporte fue enviado a Gerencia.')
            return redirect('finanzas:factura_detalle', pk=documento.pk)
    else:
        formulario_observacion = ObservacionFacturaForm()

    return render(request, 'finanzas/factura_detalle.html', {
        'titulo': f'{documento.get_tipo_documento_display()} N° {documento.numero_documento}',
        'documento': documento,
        'detalles': detalles,
        'formulario_observacion': formulario_observacion,
        'observaciones': documento.observaciones_finanzas.select_related('usuario').all(),
    })


@rol_requerido('finanzas')
@require_GET
def lista_pagos_finanzas(request):
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    pagos = PagoProveedor.objects.select_related(
        'documento',
        'documento__proveedor',
        'usuario',
    )
    if q:
        pagos = pagos.filter(
            Q(documento__numero_documento__icontains=q)
            | Q(documento__proveedor__razon_social__icontains=q)
        )
    if estado in PagoProveedor.Estado.values:
        pagos = pagos.filter(estado=estado)

    return render(request, 'finanzas/pagos_lista.html', {
        'titulo': 'Pagos a Proveedores',
        'pagos': pagos,
        'q': q,
        'estado_seleccionado': estado,
        'estados': PagoProveedor.Estado.choices,
    })


def _guardar_pago_finanzas(request, pago=None):
    formulario = PagoProveedorForm(request.POST or None, instance=pago)
    if request.method == 'POST' and formulario.is_valid():
        pago_guardado = formulario.save(commit=False)
        if pago is None:
            pago_guardado.usuario = request.user
        pago_guardado.save()
        accion = 'actualizado' if pago else 'registrado'
        messages.success(request, f'El pago fue {accion} correctamente.')
        return redirect('finanzas:pagos_lista')

    return render(request, 'finanzas/pago_form.html', {
        'titulo': 'Editar pago' if pago else 'Registrar pago',
        'formulario': formulario,
        'pago': pago,
    })


@rol_requerido('finanzas')
@require_http_methods(['GET', 'POST'])
def crear_pago_finanzas(request):
    return _guardar_pago_finanzas(request)


@rol_requerido('finanzas')
@require_http_methods(['GET', 'POST'])
def editar_pago_finanzas(request, pk):
    pago = get_object_or_404(
        PagoProveedor.objects.select_related('documento', 'usuario'),
        pk=pk,
    )
    return _guardar_pago_finanzas(request, pago=pago)


@rol_requerido('finanzas')
def lista_entidades_finanzas(request):
    """
    Lista de proveedores y clientes mandantes bajo /finanzas/entidades/,
    reutilizando los modelos de apps/entidades y calculando si cada registro
    se puede borrar físicamente (sin documentos ni obras asociadas).
    """
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()

    entidades = (
        Proveedor.objects
        .prefetch_related('contactos', 'cuentas')
        .annotate(
            num_documentos=Count('documentos_entrada', distinct=True),
            num_obras=Count('obras', distinct=True),
        )
    )

    if tipo in Proveedor.Tipo.values:
        entidades = entidades.filter(tipo=tipo)

    if q:
        filtro = Q(razon_social__icontains=q) | Q(giro__icontains=q) | Q(rut__icontains=q)
        rut_limpio = re.sub(r'[^0-9K]', '', q.upper())
        if rut_limpio and re.fullmatch(r'[0-9.\-kK\s]+', q):
            entidades = entidades.annotate(
                rut_sin_formato=Replace(
                    Replace('rut', Value('.'), Value('')),
                    Value('-'),
                    Value(''),
                )
            )
            filtro |= Q(rut_sin_formato__icontains=rut_limpio)
        entidades = entidades.filter(filtro)

    lista_entidades = list(entidades)
    for entidad in lista_entidades:
        entidad.puede_borrarse = (entidad.num_documentos == 0 and entidad.num_obras == 0)

    contexto = {
        'titulo': 'Proveedores y Mandantes',
        'entidades': lista_entidades,
        'q': q,
        'tipo_seleccionado': tipo,
        'tipos': Proveedor.Tipo.choices,
    }
    return render(request, 'finanzas/entidades_lista.html', contexto)


def _guardar_entidad_finanzas(request, instancia=None):
    """
    Crea o edita una ficha de Proveedor/Mandante junto con sus contactos
    y cuentas bancarias dentro de una transacción atómica.
    """
    es_edicion = instancia is not None
    entidad = instancia if es_edicion else Proveedor()

    if request.method == 'POST':
        form = ProveedorForm(request.POST, instance=entidad)
        contactos_formset = ContactoFormSet(request.POST, instance=entidad)
        cuentas_formset = CuentaFormSet(request.POST, instance=entidad)

        form_valido = form.is_valid()
        contactos_validos = contactos_formset.is_valid()
        cuentas_validas = cuentas_formset.is_valid()

        if form_valido and contactos_validos and cuentas_validas:
            with transaction.atomic():
                entidad = form.save()
                contactos_formset.instance = entidad
                contactos_formset.save()
                cuentas_formset.instance = entidad
                cuentas_formset.save()

            accion = "actualizada" if es_edicion else "registrada"
            messages.success(request, f"Ficha de {entidad.razon_social} {accion} con éxito.")
            return redirect('finanzas:entidades_lista')

        messages.error(request, "Por favor corrige los errores del formulario.")
    else:
        form = ProveedorForm(instance=entidad)
        contactos_formset = ContactoFormSet(instance=entidad)
        cuentas_formset = CuentaFormSet(instance=entidad)

    contexto = {
        'titulo': f"Editar Ficha: {instancia.razon_social}" if es_edicion else "Nueva Ficha de Proveedor / Mandante",
        'form': form,
        'contactos_formset': contactos_formset,
        'cuentas_formset': cuentas_formset,
        'es_edicion': es_edicion,
        'entidad': instancia,
    }
    return render(request, 'finanzas/entidad_form.html', contexto)


@rol_requerido('finanzas')
def crear_entidad_finanzas(request):
    return _guardar_entidad_finanzas(request)


@rol_requerido('finanzas')
def editar_entidad_finanzas(request, pk):
    entidad = get_object_or_404(Proveedor, pk=pk)
    return _guardar_entidad_finanzas(request, instancia=entidad)


@rol_requerido('finanzas')
@require_POST
def cambiar_estado_entidad_finanzas(request, pk):
    """Activa o desactiva un proveedor o mandante sin eliminarlo físicamente."""
    entidad = get_object_or_404(Proveedor, pk=pk)
    entidad.activo = not entidad.activo
    entidad.save(update_fields=['activo'])

    estado_txt = "activada" if entidad.activo else "desactivada"
    messages.success(request, f"Ficha de {entidad.razon_social} {estado_txt}.")
    return redirect('finanzas:entidades_lista')


@rol_requerido('finanzas')
def eliminar_entidad_finanzas(request, pk):
    """
    Pantalla de confirmación y borrado físico condicional:
    solo permite borrar físicamente si la entidad NO tiene documentos ni obras asociadas.
    """
    entidad = get_object_or_404(
        Proveedor.objects.prefetch_related('contactos', 'cuentas'),
        pk=pk,
    )
    num_documentos = entidad.documentos_entrada.count()
    num_obras = entidad.obras.count()
    puede_borrarse = (num_documentos == 0 and num_obras == 0)

    if request.method == 'POST':
        if not puede_borrarse:
            messages.error(
                request,
                f"No se puede borrar físicamente a {entidad.razon_social} porque tiene registros asociados "
                f"({num_documentos} documento(s) y {num_obras} obra(s)). Use Desactivar en su lugar."
            )
            return redirect('finanzas:entidades_lista')

        nombre = entidad.razon_social
        entidad.delete()
        messages.success(request, f"Ficha de {nombre} eliminada definitivamente.")
        return redirect('finanzas:entidades_lista')

    contexto = {
        'titulo': f"Confirmar eliminación: {entidad.razon_social}",
        'entidad': entidad,
        'num_documentos': num_documentos,
        'num_obras': num_obras,
        'puede_borrarse': puede_borrarse,
    }
    return render(request, 'finanzas/entidad_confirmar_eliminar.html', contexto)


# ==============================================================================
# ETAPA 3 - PRESUPUESTOS DE OBRAS (listar obras y editar presupuesto_total)
# ==============================================================================

@rol_requerido('finanzas')
def lista_presupuestos_finanzas(request):
    """
    Lista todas las obras registradas junto con su cliente mandante y su
    presupuesto_total (sin permitir crear obras desde Finanzas).
    """
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()

    obras = Obra.objects.select_related('mandante').all()

    if estado in Obra.Estado.values:
        obras = obras.filter(estado=estado)

    if q:
        obras = obras.filter(
            Q(nombre__icontains=q)
            | Q(mandante__razon_social__icontains=q)
            | Q(mandante__rut__icontains=q)
        )

    total_presupuestos = obras.aggregate(total=Sum('presupuesto_total'))['total'] or Decimal('0.00')

    lista_obras = list(obras)
    for obra in lista_obras:
        tiene_movs = _obra_tiene_movimientos(obra)
        obra.tiene_movimientos = tiene_movs
        obra.puede_borrar_presupuesto = (
            obra.presupuesto_total > 0
            and obra.estado != Obra.Estado.CERRADA
            and not tiene_movs
        )

    contexto = {
        'titulo': 'Presupuestos de Obras',
        'obras': lista_obras,
        'q': q,
        'estado_seleccionado': estado,
        'estados': Obra.Estado.choices,
        'total_presupuestos': total_presupuestos,
    }
    return render(request, 'finanzas/presupuestos_lista.html', contexto)


@rol_requerido('finanzas')
def editar_presupuesto_finanzas(request, pk):
    """
    Edita únicamente el campo presupuesto_total de una Obra existente,
    validando que no sea negativo.
    """
    obra = get_object_or_404(Obra.objects.select_related('mandante'), pk=pk)

    if request.method == 'POST':
        form = PresupuestoObraForm(request.POST, instance=obra)
        if form.is_valid():
            obra.presupuesto_total = form.cleaned_data['presupuesto_total']
            obra.save(update_fields=['presupuesto_total'])
            messages.success(
                request,
                f"Presupuesto de la obra '{obra.nombre}' actualizado a ${obra.presupuesto_total:,.2f}."
            )
            return redirect('finanzas:presupuestos_lista')
        messages.error(request, "Por favor corrige los errores en el monto del presupuesto.")
    else:
        form = PresupuestoObraForm(instance=obra)

    contexto = {
        'titulo': f"Editar Presupuesto: {obra.nombre}",
        'obra': obra,
        'form': form,
    }
    return render(request, 'finanzas/presupuesto_form.html', contexto)


@rol_requerido('finanzas')
def eliminar_presupuesto_finanzas(request, pk):
    """
    Pantalla de confirmación aparte para dejar en $0 el presupuesto_total de una
    obra (sin borrar la obra), solo permitido si la obra no está cerrada ni tiene
    movimientos de inventario asociados.
    """
    obra = get_object_or_404(Obra.objects.select_related('mandante'), pk=pk)
    tiene_movs = _obra_tiene_movimientos(obra)
    puede_borrarse = (
        obra.presupuesto_total > 0
        and obra.estado != Obra.Estado.CERRADA
        and not tiene_movs
    )

    if request.method == 'POST':
        if not puede_borrarse:
            messages.error(
                request,
                f"No se puede borrar el presupuesto de '{obra.nombre}' porque la obra está cerrada "
                f"o ya registra movimientos asociados."
            )
            return redirect('finanzas:presupuestos_lista')

        obra.presupuesto_total = Decimal('0.00')
        obra.save(update_fields=['presupuesto_total'])
        messages.success(
            request,
            f"El presupuesto de la obra '{obra.nombre}' fue dejado en $0.00."
        )
        return redirect('finanzas:presupuestos_lista')

    contexto = {
        'titulo': f"Confirmar borrado de presupuesto: {obra.nombre}",
        'obra': obra,
        'tiene_movimientos': tiene_movs,
        'puede_borrarse': puede_borrarse,
    }
    return render(request, 'finanzas/presupuesto_confirmar_eliminar.html', contexto)
