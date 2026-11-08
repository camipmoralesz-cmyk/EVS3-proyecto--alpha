from django.core.exceptions import ValidationError
from django.test import TestCase

from .validators import (
    calcular_dv,
    formatear_rut,
    normalizar_rut,
    rut_canonico,
    validar_rut,
)


class ValidadorRutTests(TestCase):
    """Pruebas unitarias del RUT chileno (criterio de aceptación 1 de HU-07)."""

    def test_rut_validos(self):
        validos = [
            '12.345.678-5',
            '76.543.210-3',
            '77.987.654-3',
            '11.111.111-1',
            '1.000.005-K',
            '1.000.005-k',   # acepta la k minúscula
            '76543210-3',    # acepta sin puntos
        ]
        for rut in validos:
            with self.subTest(rut=rut):
                validar_rut(rut)  # no debe lanzar excepción

    def test_rut_con_dv_incorrecto(self):
        # 76.543.210 -> DV correcto es 3 ; 76.123.456 -> DV correcto es 0
        for rut in ['76.543.210-1', '76.123.456-7']:
            with self.subTest(rut=rut):
                with self.assertRaisesMessage(ValidationError, 'dígito verificador'):
                    validar_rut(rut)

    def test_rut_con_formato_invalido(self):
        for rut in ['', 'abc', '1-9', '123']:
            with self.subTest(rut=rut):
                with self.assertRaises(ValidationError):
                    validar_rut(rut)

    def test_calcular_dv(self):
        self.assertEqual(calcular_dv('12345678'), '5')
        self.assertEqual(calcular_dv('76543210'), '3')
        self.assertEqual(calcular_dv('76123456'), '0')  # resto 11 -> "0"
        self.assertEqual(calcular_dv('1000005'), 'K')   # resto 10 -> "K"

    def test_normalizar_rut(self):
        self.assertEqual(normalizar_rut('76.543.210-3'), '76543210-3')
        self.assertEqual(normalizar_rut(' 1.000.005-k '), '1000005-K')
        self.assertEqual(normalizar_rut('765432103'), '76543210-3')
        self.assertEqual(normalizar_rut(None), '')

    def test_formatear_rut(self):
        self.assertEqual(formatear_rut('12345678-5'), '12.345.678-5')
        self.assertEqual(formatear_rut('1000005k'), '1.000.005-K')
        # Si no parece RUT, se devuelve normalizado sin fallar
        self.assertEqual(formatear_rut('123'), '12-3')

    def test_rut_canonico_unifica_formatos(self):
        self.assertEqual(rut_canonico('76543210-3'), '76.543.210-3')
        self.assertEqual(rut_canonico('76.543.210-3'), '76.543.210-3')
        self.assertEqual(rut_canonico('76543210-3'), rut_canonico('76.543.210-3'))
