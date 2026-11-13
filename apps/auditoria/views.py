from django.shortcuts import render


def lista_auditoria(request):
    return render(request, 'auditoria/lista_auditoria.html')