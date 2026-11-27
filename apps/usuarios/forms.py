from django import forms
from django.contrib.auth import authenticate, get_user_model

from .roles import ROLES, normalizar_rol_id, roles_de, tiene_rol


def rol_principal(user):
    """Rol con que se arma el panel del usuario. Gerencia tiene prioridad (y todo
    superusuario entra como Gerencia); si hay varios grupos manda el orden de ROLES."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'gerencia'
    roles = roles_de(user)
    return roles[0]['id'] if roles else None


def rol_activo(user, rol_seleccionado=None):
    """Rol con que trabaja la sesión: el guardado al iniciar sesión si el usuario aún
    lo tiene; si no, su rol principal. Lo usan el destino post-login y el sidebar."""
    canon = normalizar_rol_id(rol_seleccionado)
    if canon and tiene_rol(user, canon):
        return canon
    return rol_principal(user)


class LoginForm(forms.Form):
    username = forms.CharField(
        label='Nombre de usuario o correo',
        widget=forms.TextInput(attrs={
            'autocomplete': 'username',
            'placeholder': 'ejemplo@frioyagroindustria.cl',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': '••••••••',
        }),
    )
    rol = forms.ChoiceField(
        label='Ingresar como',
        choices=[(r['id'], f"{r['name']} ({r['badge']})") for r in ROLES],
        required=False,  # el login lo detecta solo; se mantiene por compatibilidad
    )
    recordarme = forms.BooleanField(label='Recordarme en este equipo', required=False)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None
        # 'credenciales' = usuario/clave incorrectos, 'rol' = no tiene ese rol
        self.error_tipo = None

    def clean(self):
        datos = super().clean()
        ident = datos.get('username')
        clave = datos.get('password')
        rol = datos.get('rol')
        if not (ident and clave):
            return datos

        username = ident
        if '@' in ident:
            User = get_user_model()
            u = User.objects.filter(email__iexact=ident).first()
            if u:
                username = u.get_username()

        user = authenticate(self.request, username=username, password=clave)
        if user is None:
            self.error_tipo = 'credenciales'
            raise forms.ValidationError('Usuario o contraseña incorrectos.')

        if rol:
            if not tiene_rol(user, rol):
                self.error_tipo = 'rol'
                raise forms.ValidationError(
                    'Tu cuenta no tiene permisos para ingresar con el rol seleccionado.'
                )
        else:
            rol = rol_principal(user)
            if rol is None:
                self.error_tipo = 'rol'
                raise forms.ValidationError('Tu cuenta no tiene permisos ni un rol asignado.')
            datos['rol'] = rol

        self.user = user
        return datos
