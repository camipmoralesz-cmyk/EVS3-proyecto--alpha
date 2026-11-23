from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.catalogo.models import Articulo
from apps.usuarios.roles import rol_requerido, tiene_rol
from .forms import ObraForm
from .models import HojaServicioObra, Obra, SolicitudMaterialObra


def _obras_del_supervisor(user):
    """Filtra solo las obras asignadas al supervisor (o todas si es superuser/gerencia)."""
    qs = Obra.objects.select_related('mandante').all()
    if not user.is_superuser and hasattr(Obra, 'supervisor'):
        qs = qs.filter(supervisor=user)
    return qs


@login_required
def lista_obras(request):
    obras = _obras_del_supervisor(request.user)
    puede_administrar = tiene_rol(request.user, 'finanzas', 'gerencia')
    return render(request, 'obras/lista_obras.html', {
        'obras': obras,
        'puede_administrar': puede_administrar,
    })


@login_required
def detalle_obra(request, pk):
    obra = get_object_or_404(_obras_del_supervisor(request.user), pk=pk)
    solicitudes = obra.solicitudes_materiales.select_related('articulo', 'solicitado_por').all()
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
            for _, errores in e.message_dict.items():
                for error in errores:
                    messages.error(request, error)
        return redirect('obras:detalle_obra', pk=obra.pk)

    return render(request, 'obras/detalle_obra.html', {
        'obra': obra,
        'solicitudes': solicitudes,
        'hojas': hojas,
        'puede_administrar': puede_administrar,
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


@login_required
def lista_solicitudes(request):
    obras = _obras_del_supervisor(request.user)
    articulos = Articulo.objects.all().order_by('nombre')
    solicitudes = SolicitudMaterialObra.objects.select_related(
        'obra', 'articulo', 'solicitado_por'
    ).filter(obra__in=obras).order_by('-id')

    if request.method == 'POST':
        obra_id = request.POST.get('obra')
        articulo_id = request.POST.get('articulo')
        cantidad = request.POST.get('cantidad')
        sector = request.POST.get('sector', '').strip()
        observaciones = request.POST.get('observaciones', '').strip()

        if not observaciones:
            observaciones = (
                f'Solicitud para sector/ubicación: {sector}'
                if sector
                else 'Solicitud de material desde terreno'
            )
        obra = get_object_or_404(obras, pk=obra_id)
        articulo = get_object_or_404(Articulo, pk=articulo_id)

        datos = {
            'obra': obra,
            'articulo': articulo,
            'cantidad': cantidad,
            'solicitado_por': request.user,
        }
        for campo_ubicacion in ('sector', 'ubicacion', 'sector_ubicacion'):
            if hasattr(SolicitudMaterialObra, campo_ubicacion) and sector:
                datos[campo_ubicacion] = sector

        solicitud = SolicitudMaterialObra(**datos)
        try:
            solicitud.full_clean()
            solicitud.save()
            messages.success(request, 'Solicitud de material enviada a Bodega correctamente (pendiente de despacho).')
        except ValidationError as e:
            for _, errores in e.message_dict.items():
                for error in errores:
                    messages.error(request, error)
        return redirect('obras:lista_solicitudes')

    return render(request, 'obras/solicitudes.html', {
        'obras': obras,
        'articulos': articulos,
        'solicitudes': solicitudes,
    })


@login_required
def lista_hojas_servicio(request):
    obras = _obras_del_supervisor(request.user)
    hojas = HojaServicioObra.objects.select_related('obra').filter(obra__in=obras).order_by('-id')

    if request.method == 'POST':
        obra_id = request.POST.get('obra')
        sector = request.POST.get('sector', '').strip() or 'General'
        descripcion = request.POST.get('descripcion', '').strip()

        obra = get_object_or_404(obras, pk=obra_id)
        tecnico = request.POST.get('tecnico_responsable', '').strip() or (
            request.user.get_full_name() or request.user.username
        )
        horas_raw = request.POST.get('horas_invertidas', '1').strip() or '1'
        try:
            horas = Decimal(horas_raw)
            if horas <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            horas = Decimal('1.00')

        descripcion_final = f"[{sector}] {descripcion}" if sector else descripcion
        datos = {
            'obra': obra,
            'tecnico_responsable': tecnico[:120],
            'descripcion_trabajo': descripcion_final,
            'horas_invertidas': horas,
            'fecha_servicio': timezone.localdate(),
            'registrado_por': request.user,
            'sector': sector,
        }

        hoja = HojaServicioObra(**datos)
        try:
            hoja.full_clean()
            hoja.save()
            messages.success(request, 'Hoja de servicio registrada correctamente.')
        except ValidationError as e:
            for _, errores in e.message_dict.items():
                for error in errores:
                    messages.error(request, error)
        return redirect('obras:lista_hojas_servicio')

    return render(request, 'obras/hojas_servicio.html', {
        'obras': obras,
        'hojas': hojas,
    })


@login_required
def kardex_lectura(request):
    articulos = Articulo.objects.select_related('categoria').all().order_by('nombre')
    return render(request, 'obras/kardex_lectura.html', {
        'articulos': articulos,
    })