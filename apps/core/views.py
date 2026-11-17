from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.apps import apps
from django.utils import timezone

from apps.catalogo.models import Articulo

# Detecta automáticamente el modelo de Kardex/Movimientos en la app inventario
def obtener_modelo_kardex():
    app_models = apps.get_app_config('inventario').get_models()
    for m in app_models:
        nombre = m.__name__.lower()
        if 'movimiento' in nombre or 'kardex' in nombre or 'cardex' in nombre:
            return m
    return None

ROLES_SISTEMA = [
    ('Administrador General', 'Administrador General / Gerencia'),
    ('Administrativo Finanzas', 'Administrador / Finanzas'),
    ('Bodega Logistica', 'Administrador de Bodega / Logística'),
    ('Supervisor de Obra', 'Supervisor de Obra'),
    ('Tecnico', 'Técnico (App Móvil)'),
    ('Auditor', 'Auditor (Consultas)'),
]

@login_required
def dashboard(request):
    articulos = Articulo.objects.all()
    total_articulos = articulos.count()
    
    # Artículos con stock actual <= stock mínimo (HU-11)
    articulos_criticos = articulos.filter(stock_actual__lte=F('stock_minimo'))
    alertas_stock = articulos_criticos.count()
    
    ModeloKardex = obtener_modelo_kardex()
    if ModeloKardex:
        ultimos_movimientos = ModeloKardex.objects.select_related('articulo').order_by('-id')[:8]
        movimientos_hoy = ModeloKardex.objects.count()
    else:
        ultimos_movimientos = []
        movimientos_hoy = 0

    context = {
        'total_articulos': total_articulos,
        'alertas_stock': alertas_stock,
        'articulos_criticos': articulos_criticos[:5],
        'obras_activas': 4,
        'movimientos_hoy': movimientos_hoy,
        'ultimos_movimientos': ultimos_movimientos,
    }
    return render(request, 'core/dashboard.html', context)


# ==========================================
# 1. GESTIÓN DE USUARIOS Y ROLES (RBAC)
# ==========================================
@login_required
def gestion_usuarios(request):
    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        if accion == 'crear':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            password = request.POST.get('password', '')
            rol_nombre = request.POST.get('rol', '')

            if User.objects.filter(username=username).exists():
                messages.error(request, f'El nombre de usuario "{username}" ya está registrado.')
            else:
                user = User.objects.create_user(
                    username=username, email=email, password=password,
                    first_name=first_name, last_name=last_name
                )
                if rol_nombre:
                    grupo, _ = Group.objects.get_or_create(name=rol_nombre)
                    user.groups.add(grupo)
                messages.success(request, f'Empleado {username} registrado con rol {rol_nombre}.')
            return redirect('core:gestion_usuarios')

        elif accion == 'cambiar_rol':
            user_id = request.POST.get('user_id')
            nuevo_rol = request.POST.get('rol')
            u = get_object_or_404(User, pk=user_id)
            u.groups.clear()
            if nuevo_rol:
                grupo, _ = Group.objects.get_or_create(name=nuevo_rol)
                u.groups.add(grupo)
            messages.success(request, f'Rol de {u.username} actualizado a {nuevo_rol}.')
            return redirect('core:gestion_usuarios')

        elif accion == 'toggle_estado':
            user_id = request.POST.get('user_id')
            u = get_object_or_404(User, pk=user_id)
            if u != request.user:
                u.is_active = not u.is_active
                u.save()
                estado_txt = "activado" if u.is_active else "bloqueado"
                messages.info(request, f'Usuario {u.username} {estado_txt}.')
            else:
                messages.warning(request, 'No puedes desactivar tu propia cuenta.')
            return redirect('core:gestion_usuarios')

    usuarios = User.objects.prefetch_related('groups').all().order_by('-date_joined')
    return render(request, 'core/gestion_usuarios.html', {
        'usuarios': usuarios,
        'roles': ROLES_SISTEMA
    })


# ==========================================
# 2. PANEL DE ALERTAS DE STOCK (HU-11)
# ==========================================
@login_required
def panel_alertas_stock(request):
    categoria_q = request.GET.get('categoria', '')
    articulos_alerta = Articulo.objects.filter(stock_actual__lte=F('stock_minimo'))
    
    if categoria_q:
        articulos_alerta = articulos_alerta.filter(categoria__icontains=categoria_q)

    return render(request, 'core/alertas_stock.html', {
        'articulos_alerta': articulos_alerta,
        'categoria_q': categoria_q
    })


# ==========================================
# 3. AUDITORÍA KARDEX Y CONTRA-ASIENTO (HU-12)
# ==========================================
@login_required
def auditoria_kardex(request):
    q = request.GET.get('q', '').strip()
    ModeloKardex = obtener_modelo_kardex()
    
    if ModeloKardex:
        movimientos = ModeloKardex.objects.select_related('articulo').all().order_by('-id')
        if q:
            movimientos = movimientos.filter(articulo__nombre__icontains=q)
    else:
        movimientos = []

    return render(request, 'core/auditoria_kardex.html', {
        'movimientos': movimientos,
        'q': q
    })


@login_required
@transaction.atomic
def anular_movimiento_kardex(request, mov_id):
    ModeloKardex = obtener_modelo_kardex()
    if not ModeloKardex:
        messages.error(request, 'Modelo de Kardex no encontrado.')
        return redirect('core:auditoria_kardex')

    mov_original = get_object_or_404(ModeloKardex, pk=mov_id)
    
    if request.method == 'POST':
        motivo = request.POST.get('motivo', '').strip()
        if not motivo:
            messages.error(request, 'El motivo de ajuste es obligatorio para generar un contra-asiento.')
            return redirect('core:auditoria_kardex')

        articulo = mov_original.articulo
        cantidad = mov_original.cantidad
        tipo_orig = str(getattr(mov_original, 'tipo_movimiento', getattr(mov_original, 'tipo', ''))).upper()

        if 'ENTRADA' in tipo_orig or 'INGRESO' in tipo_orig:
            articulo.stock_actual -= cantidad
            tipo_reversa = 'CONTRA_ASIENTO_INGRESO'
        else:
            articulo.stock_actual += cantidad
            tipo_reversa = 'CONTRA_ASIENTO_EGRESO'
        articulo.save()

        ahora_str = timezone.now().strftime('%d/%m/%Y %H:%M')
        bitacora_detalle = f"ANULADO ID#{mov_original.id} | Por: {request.user.username} | Fecha: {ahora_str} | Motivo: {motivo}"

        nuevo_mov = ModeloKardex()
        nuevo_mov.articulo = articulo
        nuevo_mov.cantidad = cantidad
        if hasattr(nuevo_mov, 'tipo_movimiento'):
            nuevo_mov.tipo_movimiento = tipo_reversa
        elif hasattr(nuevo_mov, 'tipo'):
            nuevo_mov.tipo = tipo_reversa
            
        if hasattr(nuevo_mov, 'documento'):
            nuevo_mov.documento = bitacora_detalle
        elif hasattr(nuevo_mov, 'referencia'):
            nuevo_mov.referencia = bitacora_detalle
            
        if hasattr(nuevo_mov, 'usuario'):
            nuevo_mov.usuario = request.user
        nuevo_mov.save()

        messages.success(
            request, 
            f'Contra-asiento #{nuevo_mov.id} registrado en bitácora ({bitacora_detalle}).'
        )
        return redirect('core:auditoria_kardex')

    return redirect('core:auditoria_kardex')


# ==========================================
# 4. APROBACIÓN DE INVENTARIOS FÍSICOS Y DE OBRA
# ==========================================
@login_required
def aprobacion_inventarios(request):
    articulos = Articulo.objects.all()
    if request.method == 'POST':
        tipo_acta = request.POST.get('tipo_acta', 'Inventario Físico General')
        observacion = request.POST.get('observacion', 'Aprobado conforme por Gerencia.')
        ahora = timezone.now().strftime('%d/%m/%Y %H:%M')
        messages.success(
            request,
            f'Acta de "{tipo_acta}" APROBADA oficialmente por {request.user.username} el {ahora}. ({observacion})'
        )
        return redirect('core:aprobacion_inventarios')

    return render(request, 'core/aprobacion_inventarios.html', {
        'articulos': articulos,
    })


# ==========================================
# 5. CONSULTAS GLOBALES DE SOLO LECTURA
# ==========================================
@login_required
def consulta_lectura(request, seccion):
    registros = []
    titulo_seccion = "Consulta General"

    if seccion == 'catalogo':
        titulo_seccion = "Catálogo Maestro de Artículos (Solo Lectura)"
        registros = Articulo.objects.all()
    elif seccion == 'facturas':
        titulo_seccion = "Documentos Tributarios y Facturas (Solo Lectura)"
        for m in apps.get_app_config('inventario').get_models():
            if 'documento' in m.__name__.lower() and 'detalle' not in m.__name__.lower():
                registros = m.objects.all().order_by('-id')
                break
    elif seccion == 'entidades':
        titulo_seccion = "Directorio de Proveedores y Mandantes (Solo Lectura)"
        for m in apps.get_app_config('entidades').get_models():
            if 'entidad' in m.__name__.lower() or 'proveedor' in m.__name__.lower():
                registros = m.objects.all()
                break

    return render(request, 'core/consulta_lectura.html', {
        'seccion': seccion,
        'titulo_seccion': titulo_seccion,
        'registros': registros,
    })