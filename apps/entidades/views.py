from django.shortcuts import render

def lista_entidades(request):
    return render(request, 'entidades/lista_entidades.html')
