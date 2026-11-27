import re
from django.core.exceptions import ValidationError


class PasswordStrengthValidator:

    def validate(self, password, user=None):

        if not re.search(r"[A-Z]", password):
            raise ValidationError(
                "La contraseña debe contener al menos una letra mayúscula."
            )

        if not re.search(r"[a-z]", password):
            raise ValidationError(
                "La contraseña debe contener al menos una letra minúscula."
            )

        if not re.search(r"[0-9]", password):
            raise ValidationError(
                "La contraseña debe contener al menos un número."
            )

        if not re.search(r"[^A-Za-z0-9]", password):
            raise ValidationError(
                "La contraseña debe contener al menos un carácter especial."
            )

    def get_help_text(self):
        return (
            "La contraseña debe incluir mayúsculas, minúsculas, "
            "números y caracteres especiales."
        )