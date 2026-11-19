from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from .models import Obra, SolicitudMaterialObra, HojaServicioObra

@login_required
def lista_obras(request):
    # El supervisor ve todas las obras o las filtradas según su usuario
    obras = Obra.objects.select_related('mandante').all()
    return render(request, 'obras/lista_obras.html', {'obras': obras})

@login_required
def detalle_obra(request, obra_id):
    obra = get_object_or_404(Obra.objects.select_related('mandante'), pk=obra_id)
    solicitudes = obra.solicitudes_materiales.select_related('articulo', 'solicitado_por').all()
    
    if request.method == 'POST':
        nuevo_estado = request.POST.get('estado')
        obra.estado = nuevo_estado
        try:
            obra.full_clean()  # Dispara la validación del método clean() (ej: bloquear cierre con solicitudes pendientes)
            obra.save()
            messages.success(request, f'Estado de la obra actualizado correctamente a {obra.get_estado_display()}.')
        except ValidationError as e:
            for campo, errores in e.message_dict.items():
                for error in errores:
                    messages.error(request, error)
        return redirect('obras:detalle_obra', obra_id=obra.id)

    context = {
        'obra': obra,
        'solicitudes': solicitudes,
    }
    return render(request, 'obras/detalle_obra.html', context)