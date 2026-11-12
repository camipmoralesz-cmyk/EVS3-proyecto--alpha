from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.usuarios.roles import ROLES


class Command(BaseCommand):
    help = 'Crea los grupos de roles de FYAG. Con --demo crea además un usuario de prueba por rol.'

    def add_arguments(self, parser):
        parser.add_argument('--demo', action='store_true',
                            help='Crea usuarios de prueba (solo para desarrollo).')

    def handle(self, *args, **opts):
        User = get_user_model()
        for rol in ROLES:
            grupo, creado = Group.objects.get_or_create(name=rol['id'])
            self.stdout.write(f"{'Creado' if creado else 'Existe'}: grupo '{grupo.name}'")
            if opts['demo']:
                user, nuevo = User.objects.get_or_create(
                    username=rol['id'],
                    defaults={'email': f"{rol['id']}@frioyagroindustria.cl"},
                )
                if nuevo:
                    user.set_password('Alpha2026!')
                    user.save()
                user.groups.add(grupo)
                self.stdout.write(f"  usuario demo '{rol['id']}' (clave Alpha2026!)")