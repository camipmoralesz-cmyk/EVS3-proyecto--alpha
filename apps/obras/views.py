from django.shortcuts import render


def despachos(request):
    return render(request, 'obras/despachos.html')
