from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.catalogo.models import Articulo
from apps.inventario.models import DetalleSolicitud, MovimientoInventario, SolicitudDespacho
from apps.usuarios.roles import rol_requerido, tiene_rol
from .forms import ObraForm
from .models import HojaServicioObra, Obra, SolicitudMaterialObra


def _obras_del_supervisor(user):
    """Obras visibles para el usuario: Gerencia/Finanzas ven todas; el supervisor ve
    las suyas y las que aún no tienen responsable asignado."""
    qs = Obra.objects.select_related('mandante', 'supervisor').all()
    if user.is_superuser or tiene_rol(user, 'gerencia', 'finanzas'):
        return qs
    if tiene_rol(user, 'supervisor'):
        return qs.filter(Q(supervisor=user) | Q(supervisor__isnull=True))
    return qs


def _despachos_de(obras):
    """Pedidos que Bodega tiene registrados para las obras (con su estado real)."""
    return (SolicitudDespacho.objects
            .filter(obra__in=obras)
            .select_related('obra', 'solicitante', 'despacho')
            .prefetch_related('detalles__articulo')
            .order_by('-fecha_solicitud'))


def _puede_ver_vale(user):
    # El vale de salida lo abren los mismos roles que leen el Cardex de Bodega
    return tiene_rol(user, 'bodega', 'gerencia', 'finanzas')


def _mostrar_errores(request, error):
    for _, errores in error.message_dict.items():
        for mensaje in errores:
            messages.error(request, mensaje)


@rol_requerido('supervisor', 'gerencia', 'finanzas')
def lista_obras(request):
    obras = _obras_del_supervisor(request.user)
    puede_administrar = tiene_rol(request.user, 'finanzas', 'gerencia')
    return render(request, 'obras/lista_obras.html', {
        'obras': obras,
        'puede_administrar': puede_administrar,
    })


@rol_requerido('supervisor', 'gerencia', 'finanzas')
def detalle_obra(request, pk):
    obra = get_object_or_404(_obras_del_supervisor(request.user), pk=pk)
    despachos = _despachos_de([obra])
    hojas = HojaServicioObra.objects.filter(obra=obra).order_by('-id')
    puede_administrar = tiene_rol(request.user, 'finanzas', 'gerencia')

    if request.method == 'POST':
        nuevo_estado = request.POST.get('estado')
        obra.estado = nuevo_estado
        try:
            obra.full_clean()
            obra.save()
            messages.success(request, f'Estado de la obra actualizado correctamente a {obra.get_estado_display()}.')
        except ValidationError as e:
            _mostrar_errores(request, e)
        return redirect('obras:detalle_obra', pk=obra.pk)

    return render(request, 'obras/detalle_obra.html', {
        'obra': obra,
        'despachos': despachos,
        'hojas': hojas,
        'puede_administrar': puede_administrar,
        'puede_ver_vale': _puede_ver_vale(request.user),
    })


@rol_requerido('finanzas', 'gerencia')
def crear_obra(request):
    if request.method == 'POST':
        form = ObraForm(request.POST)
        if form.is_valid():
            obra = form.save()
            messages.success(request, 'La obra se creó correctamente.')
            return redirect('obras:detalle_obra', pk=obra.pk)
    else:
        form = ObraForm()

    return render(request, 'obras/form.html', {
        'form': form,
        'titulo': 'Registrar obra',
    })


@rol_requerido('finanzas', 'gerencia')
def editar_obra(request, pk):
    obra = get_object_or_404(Obra, pk=pk)
    if request.method == 'POST':
        form = ObraForm(request.POST, instance=obra)
        if form.is_valid():
            form.save()
            messages.success(request, 'La obra se actualizó correctamente.')
            return redirect('obras:detalle_obra', pk=obra.pk)
    else:
        form = ObraForm(instance=obra)

    return render(request, 'obras/form.html', {
        'form': form,
        'titulo': 'Editar obra',
    })


@rol_requerido('supervisor', 'gerencia')
def lista_solicitudes(request):
    obras = _obras_del_supervisor(request.user)
    articulos = Articulo.objects.filter(activo=True).order_by('nombre')
    if request.method == 'POST':
        obra = get_object_or_404(obras, pk=request.POST.get('obra'))
        articulo = get_object_or_404(Articulo, pk=request.POST.get('articulo'), activo=True)
        sector = request.POST.get('sector', '').strip()

        solicitud = SolicitudMaterialObra(
            obra=obra,
            articulo=articulo,
            cantidad=request.POST.get('cantidad'),
            solicitado_por=request.user,
        )
        try:
            solicitud.full_clean(exclude=['solicitud_despacho'])
            if obra.estado != Obra.Estado.ACTIVA:
                raise ValidationError({'obra': 'Solo se pueden solicitar materiales para obras activas.'})
            # La solicitud de terreno y el pedido que ve Bodega nacen juntos o no nacen
            with transaction.atomic():
                despacho = SolicitudDespacho.objects.create(
                    obra=obra,
                    solicitante=request.user,
                    observaciones=f'Sector: {sector}' if sector else '',
                )
                DetalleSolicitud.objects.create(
                    solicitud=despacho, articulo=articulo, cantidad=solicitud.cantidad,
                )
                solicitud.solicitud_despacho = despacho
                solicitud.save()
            messages.success(
                request,
                f'Solicitud #{despacho.pk} enviada a Bodega (pendiente de despacho).'
            )
        except ValidationError as e:
            _mostrar_errores(request, e)
        return redirect('obras:lista_solicitudes')

    return render(request, 'obras/solicitudes.html', {
        'obras': obras,
        'articulos': articulos,
        'despachos': _despachos_de(obras),
        'puede_ver_vale': _puede_ver_vale(request.user),
    })


@rol_requerido('supervisor', 'tecnico', 'gerencia')
def lista_hojas_servicio(request):
    obras = _obras_del_supervisor(request.user)
    hojas = HojaServicioObra.objects.select_related('obra').filter(obra__in=obras).order_by('-id')

    if request.method == 'POST':
        obra_id = request.POST.get('obra')
        sector = request.POST.get('sector', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()

        obra = get_object_or_404(obras, pk=obra_id)
        tecnico = request.POST.get('tecnico_responsable', '').strip() or (
            request.user.get_full_name() or request.user.username
        )
        horas_raw = request.POST.get('horas_invertidas', '1').strip() or '1'
        try:
            horas = Decimal(horas_raw.replace(',', '.'))
            if not horas.is_finite() or horas <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, 'Las horas invertidas deben ser un número mayor a cero.')
            return redirect('obras:lista_hojas_servicio')

        descripcion_final = f"[{sector}] {descripcion}" if sector else descripcion
        hoja = HojaServicioObra(
            obra=obra,
            tecnico_responsable=tecnico[:120],
            descripcion_trabajo=descripcion_final,
            horas_invertidas=horas,
            fecha_servicio=timezone.localdate(),
            registrado_por=request.user,
        )
        try:
            hoja.full_clean()
            hoja.save()
            messages.success(request, 'Hoja de servicio registrada correctamente.')
        except ValidationError as e:
            _mostrar_errores(request, e)
        return redirect('obras:lista_hojas_servicio')

    return render(request, 'obras/hojas_servicio.html', {
        'obras': obras,
        'hojas': hojas,
    })


@rol_requerido('supervisor', 'tecnico', 'gerencia')
def kardex_lectura(request):
    articulos = Articulo.objects.select_related('categoria').filter(activo=True).order_by('nombre')
    obras = _obras_del_supervisor(request.user)
    movimientos = (MovimientoInventario.objects
                   .filter(obra__in=obras)
                   .select_related('articulo', 'obra', 'usuario')
                   .order_by('-fecha', '-id')[:100])
    return render(request, 'obras/kardex_lectura.html', {
        'articulos': articulos,
        'movimientos': movimientos,
    })
