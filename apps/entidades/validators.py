"""
Utilidades para trabajar con el RUT chileno (HU-07).

Forma canónica (la que se guarda en la base de datos): con puntos y guion,
por ejemplo "76.123.456-0". Es la misma que ya usaban los datos de HU-01.
"""
import re

from django.core.exceptions import ValidationError

# Después de normalizar, un RUT válido tiene 7 u 8 dígitos, un guion y el DV.
RUT_REGEX = re.compile(r'^(\d{7,8})-([0-9K])$')


def normalizar_rut(valor):
    """
    Limpia el RUT dejando solo dígitos y la letra K, y lo devuelve como
    "cuerpo-DV" (sin puntos). Ej: "76.123.456-k" -> "76123456-K".
    """
    if valor is None:
        return ''
    limpio = re.sub(r'[^0-9K]', '', str(valor).upper())
    if len(limpio) < 2:
        # Muy corto para separar cuerpo y DV: se devuelve tal cual.
        return limpio
    return f'{limpio[:-1]}-{limpio[-1]}'


def calcular_dv(cuerpo):
    """
    Calcula el dígito verificador con el algoritmo módulo 11.
    Se recorren los dígitos de derecha a izquierda multiplicándolos por
    2, 3, 4, 5, 6, 7, 2, 3, ... se suman, y el DV es 11 - (suma % 11).
    Si da 11 el DV es "0" y si da 10 el DV es "K".
    """
    suma = 0
    peso = 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * peso
        peso = 2 if peso == 7 else peso + 1
    resultado = 11 - (suma % 11)
    if resultado == 11:
        return '0'
    if resultado == 10:
        return 'K'
    return str(resultado)


def formatear_rut(valor):
    """
    Devuelve el RUT con puntos y guion. Ej: "12345678-5" -> "12.345.678-5".
    Si el texto no tiene forma de RUT, se devuelve normalizado (sin fallar),
    para que el validador sea quien informe el error.
    """
    normalizado = normalizar_rut(valor)
    coincidencia = RUT_REGEX.match(normalizado)
    if not coincidencia:
        return normalizado
    cuerpo, dv = coincidencia.groups()
    # Agrupa de a 3 dígitos desde la derecha: 12345678 -> 12.345.678
    grupos = []
    while cuerpo:
        grupos.insert(0, cuerpo[-3:])
        cuerpo = cuerpo[:-3]
    return f"{'.'.join(grupos)}-{dv}"


def rut_canonico(valor):
    """Forma en que se guarda el RUT en la base de datos (con puntos y guion)."""
    return formatear_rut(valor)


def validar_rut(valor):
    """
    Validador de Django: lanza ValidationError si el RUT no tiene formato
    válido o si su dígito verificador no corresponde.
    Acepta el RUT con o sin puntos y con la K en minúscula o mayúscula.
    """
    normalizado = normalizar_rut(valor)
    if not normalizado:
        raise ValidationError('Debe ingresar un RUT.', code='rut_vacio')

    coincidencia = RUT_REGEX.match(normalizado)
    if not coincidencia:
        raise ValidationError(
            'Formato de RUT inválido. Use el formato 12.345.678-5.',
            code='rut_formato',
        )

    cuerpo, dv = coincidencia.groups()
    if calcular_dv(cuerpo) != dv:
        raise ValidationError(
            'El dígito verificador del RUT no es válido.',
            code='rut_dv',
        )

