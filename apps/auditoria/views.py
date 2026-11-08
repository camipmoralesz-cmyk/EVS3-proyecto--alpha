#Implementa la lógica atómica de anulación que valida el motivo, revierte el stock del artículo y registra la transacción inalterable en PostgreSQL (además del envío opcional del log de auditoría).


from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import MovimientoCardex
from .forms import AnulacionControladaForm

class EsAdministradorGeneralMixin(UserPassesTestMixin):
    """Restringe el acceso solo al Administrador General (RBAC según HU-12)."""
    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or 
            getattr(self.request.user, 'rol', '') == 'ADMINISTRADOR_GENERAL'#
            
        )

class AnularMovimientoView(LoginRequiredMixin, EsAdministradorGeneralMixin, View):
    template_name = 'auditoria/anular_movimiento.html'

    def post(self, request, *args, **kwargs):
        form = AnulacionControladaForm(request.POST)
        if form.is_valid():
            mov_id = form.cleaned_data['movimiento_id']
            motivo = form.cleaned_data['motivo_anulacion']
            
            try:
                with transaction.atomic():
                    # 1. Obtener movimiento original bloqueando la fila
                    mov_original = MovimientoCardex.objects.select_for_update().get(id=mov_id)
                    
                    if mov_original.es_reversa or hasattr(mov_original, 'contra_asiento'):
                        messages.error(request, "Este movimiento ya fue anulado o es un contra-asiento.")
                        return redirect('auditoria:lista_cardex')
                    
                    articulo = mov_original.articulo
                    
                    # 2. Calcular la cantidad inversa para restaurar el stock
                    cantidad_inversa = -mov_original.cantidad
                    nuevo_stock = articulo.stock_fisico + cantidad_inversa
                    
                    if nuevo_stock < 0:
                        messages.error(request, "No se puede anular: el stock resultante sería negativo.")
                        return redirect('auditoria:lista_cardex')
                    
                    # 3. Actualizar stock del artículo
                    articulo.stock_fisico = nuevo_stock
                    articulo.save()
                    
                    # 4. Registrar contra-asiento inalterable en Cardex
                    contra_asiento = MovimientoCardex.objects.create(
                        articulo=articulo,
                        tipo_movimiento='ANULACION',
                        cantidad=cantidad_inversa,
                        saldo_resultante=nuevo_stock,
                        valor_unitario=mov_original.valor_unitario,
                        usuario=request.user,
                        obra=mov_original.obra,
                        tecnico=mov_original.tecnico,
                        justificacion=f"ANULACIÓN de Movimiento #{mov_original.id}. Motivo: {motivo}",
                        es_reversa=True,
                        movimiento_reversado=mov_original
                    )
                    
                    messages.success(
                        request, 
                        f"Contra-asiento #{contra_asiento.id} generado exitosamente. Stock actualizado a {nuevo_stock}."
                    )
                    return redirect('auditoria:lista_cardex')
                    
            except MovimientoCardex.DoesNotExist:
                messages.error(request, "El movimiento especificado no existe.")
            except Exception as e:
                messages.error(request, f"Error al procesar la anulación: {str(e)}")
                
        return redirect('auditoria:lista_cardex')

class ListaCardexView(LoginRequiredMixin, View):
    def get(self, request):
        movimientos = MovimientoCardex.objects.select_related('articulo', 'usuario', 'obra').all()
        return render(request, 'auditoria/cardex_list.html', {'movimientos': movimientos})