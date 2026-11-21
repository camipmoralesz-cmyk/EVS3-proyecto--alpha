from datetime import timedelta

from django.db.models import F, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.catalogo.models import Articulo
from apps.inventario.models import MovimientoInventario as M, SolicitudDespacho
from apps.obras.models import Obra
from apps.usuarios.roles import rol_requerido


@rol_requerido('bodega', 'gerencia', 'finanzas', 'supervisor')
def dashboard(request):
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    articulos = Articulo.objects.filter(activo=True)
    mermas_mes = M.objects.filter(tipo_movimiento=M.TIPO_MERMA, fecha__date__gte=inicio_mes)
    contexto = {
        'total_articulos': articulos.count(),
        'alertas_stock': articulos.filter(stock_actual__lte=F('stock_minimo')).count(),
        'obras_activas': Obra.objects.filter(estado=Obra.Estado.ACTIVA).count(),
        'movimientos_hoy': M.objects.filter(fecha__date=hoy).count(),
        'solicitudes_pendientes': SolicitudDespacho.objects.filter(estado=SolicitudDespacho.Estado.PENDIENTE).count(),
        'mermas_mes': mermas_mes.count(),
        'mermas_mes_unidades': mermas_mes.aggregate(t=Sum('cantidad'))['t'] or 0,
        'ultimos_movimientos': M.objects.select_related('articulo', 'obra')[:8],
        'articulos_alerta': articulos.filter(stock_actual__lte=F('stock_minimo')).order_by('stock_actual')[:5],
    }
    return render(request, 'core/dashboard.html', contexto)
