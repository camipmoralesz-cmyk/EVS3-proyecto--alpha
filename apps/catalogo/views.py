from django.shortcuts import render

from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Articulo
from .forms import ArticuloForm

def lista_articulos(request):
    articulos = Articulo.objects.select_related('categoria').all()
    return render(request, 'catalogo/lista.html', {'articulos': articulos})

def crear_articulo(request):
    if request.method == 'POST':
        form = ArticuloForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Artículo registrado con éxito en el Catálogo Maestro.")
            return redirect('lista_articulos')
        else:
            messages.error(request, "Por favor corrige los errores del formulario.")
    else:
        form = ArticuloForm()
    
    return render(request, 'catalogo/form.html', {'form': form})