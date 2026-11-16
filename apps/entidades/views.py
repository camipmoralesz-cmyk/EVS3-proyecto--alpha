import re

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Replace
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ContactoFormSet, CuentaFormSet, ProveedorForm
from .models import Proveedor


def lista_entidades(request):
    """
    Lista las fichas con filtro por tipo (Proveedor / Mandante) y un buscador
    rápido por RUT, razón social o giro comercial (criterio 4 de HU-07).
    """
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()

    # prefetch_related trae los contactos en una sola consulta adicional, así
    # contar contactos por fila en la tabla no hace N consultas extras.
    entidades = Proveedor.objects.prefetch_related('contactos').all()

    if tipo in Proveedor.Tipo.values:
        entidades = entidades.filter(tipo=tipo)

    if q:
        filtro = Q(razon_social__icontains=q) | Q(giro__icontains=q) | Q(rut__icontains=q)
        # Si lo escrito parece un RUT (solo dígitos, puntos, guion o K), también
        # se compara quitando puntos y guion en ambos lados. Así buscar
        # "76543210" encuentra a "76.543.210-3" y viceversa.
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

    contexto = {
        'entidades': entidades,
        'q': q,
        'tipo_seleccionado': tipo,
        'tipos': Proveedor.Tipo.choices,
    }
    return render(request, 'entidades/lista.html', contexto)


def _guardar_entidad(request, instancia=None):
    """
    Lógica compartida entre crear y editar: valida los 3 formularios a la vez
    (para que el usuario vea todos los errores de una sola vez) y guarda todo
    dentro de una transacción atómica (o se guarda todo, o no se guarda nada).
    """
    es_edicion = instancia is not None
    entidad = instancia if es_edicion else Proveedor()

    if request.method == 'POST':
        form = ProveedorForm(request.POST, instance=entidad)
        contactos_formset = ContactoFormSet(request.POST, instance=entidad)
        cuentas_formset = CuentaFormSet(request.POST, instance=entidad)

        # Se evalúan los tres antes del "if" para que Django calcule los errores
        # de los tres (en Python, "a and b" no evalúa "b" si "a" ya dio False).
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
            return redirect('lista_entidades')

        messages.error(request, "Por favor corrige los errores del formulario.")
    else:
        form = ProveedorForm(instance=entidad)
        contactos_formset = ContactoFormSet(instance=entidad)
        cuentas_formset = CuentaFormSet(instance=entidad)

    contexto = {
        'form': form,
        'contactos_formset': contactos_formset,
        'cuentas_formset': cuentas_formset,
        'es_edicion': es_edicion,
        'entidad': instancia,
    }
    return render(request, 'entidades/form.html', contexto)


def crear_entidad(request):
    return _guardar_entidad(request)


def editar_entidad(request, pk):
    entidad = get_object_or_404(Proveedor, pk=pk)
    return _guardar_entidad(request, instancia=entidad)


@require_POST
def cambiar_estado_entidad(request, pk):
    """
    RF01: las fichas nunca se borran, solo se desactivan o reactivan.
    Solo acepta POST (con token CSRF) porque modifica datos.
    """
    entidad = get_object_or_404(Proveedor, pk=pk)
    entidad.activo = not entidad.activo
    entidad.save(update_fields=['activo'])

    estado_txt = "activada" if entidad.activo else "desactivada"
    messages.success(request, f"Ficha de {entidad.razon_social} {estado_txt}.")
    return redirect('lista_entidades')
