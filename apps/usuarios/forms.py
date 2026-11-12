from django import forms
from django.contrib.auth import authenticate, get_user_model

from .roles import ROLES, tiene_rol


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
        if not (ident and clave and rol):
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

        if not tiene_rol(user, rol):
            self.error_tipo = 'rol'
            raise forms.ValidationError(
                'Tu cuenta no tiene permisos para ingresar con el rol seleccionado.'
            )

        self.user = user
        return datos
