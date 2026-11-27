from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.usuarios.roles import rol_requerido
from apps.finanzas.utils import bloquear_escrituras_finanzas
from .forms import ArticuloForm, CategoriaForm
from .models import Articulo, Categoria

# Catálogo maestro: lo gestionan Bodega (crea artículos) y Finanzas (HU-06).
catalogo_escritura = rol_requerido('bodega', 'finanzas')
catalogo_lectura = rol_requerido('bodega', 'finanzas', 'gerencia', 'supervisor')


@catalogo_lectura
def lista_articulos(request):
    q = request.GET.get('q', '').strip()
    articulos = Articulo.objects.select_related('categoria').order_by('nombre')
    if q:
        articulos = articulos.filter(
            Q(codigo_interno__icontains=q) | Q(codigo_barras__icontains=q)
            | Q(nombre__icontains=q) | Q(categoria__nombre__icontains=q)
        )
    return render(request, 'catalogo/lista.html', {
        'articulos': articulos, 'q': q,
        'categorias': Categoria.objects.order_by('nombre'),
        'form_categoria': CategoriaForm(),
    })


def _guardar(request, instancia=None):
    form = ArticuloForm(request.POST or None, instance=instancia)
    if request.method == 'POST':
        if form.is_valid():
            art = form.save()
            messages.success(request, f"Artículo '{art.nombre}' guardado con éxito en el Catálogo Maestro.")
            return redirect('lista_articulos')
        messages.error(request, "Por favor corrige los errores del formulario.")
    return render(request, 'catalogo/form.html', {
        'form': form, 'es_edicion': instancia is not None, 'articulo': instancia,
    })


@catalogo_escritura
@bloquear_escrituras_finanzas
def crear_articulo(request):
    return _guardar(request)


@catalogo_escritura
@bloquear_escrituras_finanzas
def editar_articulo(request, pk):
    return _guardar(request, get_object_or_404(Articulo, pk=pk))


@catalogo_escritura
@bloquear_escrituras_finanzas
@require_POST
def cambiar_estado_articulo(request, pk):
    """Los artículos nunca se borran: se desactivan o reactivan."""
    art = get_object_or_404(Articulo, pk=pk)
    art.activo = not art.activo
    art.save(update_fields=['activo'])
    messages.success(request, f"Artículo '{art.nombre}' {'activado' if art.activo else 'desactivado'}.")
    return redirect('lista_articulos')


@catalogo_escritura
@bloquear_escrituras_finanzas
@require_POST
def crear_categoria(request):
    form = CategoriaForm(request.POST)
    if form.is_valid():
        categoria = form.save()
        messages.success(request, f"Categoría '{categoria.nombre}' creada. Ya puede asignarla a los artículos.")
    else:
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
    return redirect('lista_articulos')
