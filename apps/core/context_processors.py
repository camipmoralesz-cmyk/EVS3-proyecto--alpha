def roles_processor(request):
    if not request.user.is_authenticated:
        return {'es_admin_general': False, 'rol_usuario': 'Invitado'}
    
    grupos = list(request.user.groups.values_list('name', flat=True))
    
    # Si es superusuario o pertenece al grupo Administrador General
    es_admin_general = (
        request.user.is_superuser or 
        'Administrador General' in grupos
    )
    
    rol_actual = grupos[0] if grupos else ('Administrador General' if request.user.is_superuser else 'Operador')
    
    return {
        'es_admin_general': es_admin_general,
        'rol_usuario': rol_actual,
    }