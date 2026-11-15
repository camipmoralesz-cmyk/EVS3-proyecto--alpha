from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from .models import Obra
from .forms import ObraForm
from apps.usuarios.roles import rol_requerido, tiene_rol


@rol_requerido('supervisor', 'finanzas', 'gerencia')
def lista_obras(request):
    obras = Obra.objects.select_related('mandante').all()

    puede_administrar = tiene_rol(
        request.user,
        'finanzas',
        'gerencia'
    )

    return render(request, 'obras/lista.html', {
        'obras': obras,
        'puede_administrar': puede_administrar,
    })


@rol_requerido('supervisor', 'finanzas', 'gerencia')
def detalle_obra(request, pk):
    obra = get_object_or_404(Obra, pk=pk)

    puede_administrar = tiene_rol(
        request.user,
        'finanzas',
        'gerencia'
    )

    return render(request, 'obras/detalle.html', {
        'obra': obra,
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
        'titulo': 'Registrar obra'
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
        'titulo': 'Editar obra'
    })