from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.catalogo.models import Articulo
from .models import DocumentoEntrada, DetalleDocumento, MovimientoInventario

def calcular_descuentos_sucesivos(precio_base, desc1=0, desc2=0, desc3=0):
    """
    Calcula el precio unitario final aplicando hasta tres descuentos sucesivos independientes.
    Retorna el precio unitario final redondeado al entero más cercano (CLP).
    """
    p = Decimal(str(precio_base))
    d1 = Decimal(str(desc1 or 0))
    d2 = Decimal(str(desc2 or 0))
    d3 = Decimal(str(desc3 or 0))

    for d in (d1, d2, d3):
        if d < 0 or d > 100:
            raise ValidationError(f"El porcentaje de descuento debe estar entre 0% y 100%. Valor recibido: {d}%")
        p = p * (Decimal('1') - (d / Decimal('100')))

    # Redondeo bancario/comercial estándar para CLP
    precio_final = int(p.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return max(0, precio_final)


def calcular_subtotal_linea(precio_unitario_final, cantidad):
    """
    Calcula el subtotal de una línea multiplicando precio final por cantidad.
    """
    cant = Decimal(str(cantidad))
    if cant <= 0:
        raise ValidationError("La cantidad del ítem debe ser mayor a 0.")
    subtotal = (Decimal(precio_unitario_final) * cant).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(subtotal)


@transaction.atomic
def registrar_documento_entrada(datos_documento, lineas_detalle, usuario=None):
    """
    Registra de forma segura un documento de entrada (Factura, Boleta, Guía, Nota de Crédito)
    junto con sus líneas de detalle, actualiza el stock disponible y costos de los artículos,
    y genera el registro de auditoría en MovimientoInventario.
    
    Todo se ejecuta dentro de una transacción atómica; si cualquier línea o validación falla,
    se revierte la transacción completa.
    """
    if not lineas_detalle:
        raise ValidationError("El documento debe contener al menos una línea de detalle.")

    # 1. Crear encabezado del documento
    documento = DocumentoEntrada.objects.create(
        proveedor=datos_documento['proveedor'],
        tipo_documento=datos_documento['tipo_documento'],
        numero_documento=datos_documento['numero_documento'].strip(),
        fecha_emision=datos_documento['fecha_emision'],
        observaciones=datos_documento.get('observaciones', ''),
        registrado_por=usuario,
        monto_neto=0
    )

    es_nota_credito = (documento.tipo_documento == DocumentoEntrada.TIPO_NOTA_CREDITO)
    total_neto_acumulado = 0

    # 2. Procesar cada línea de ítem
    for linea in lineas_detalle:
        articulo_id = linea['articulo_id']
        cantidad = Decimal(str(linea['cantidad']))
        precio_base = int(linea['precio_unitario_base'])
        d1 = Decimal(str(linea.get('descuento_1_porcentaje', 0) or 0))
        d2 = Decimal(str(linea.get('descuento_2_porcentaje', 0) or 0))
        d3 = Decimal(str(linea.get('descuento_3_porcentaje', 0) or 0))

        if cantidad <= 0:
            raise ValidationError(f"La cantidad debe ser mayor a cero en todos los artículos.")

        if precio_base < 0:
            raise ValidationError("El precio base no puede ser negativo.")

        # Matemática de descuentos
        precio_final = calcular_descuentos_sucesivos(precio_base, d1, d2, d3)
        subtotal = calcular_subtotal_linea(precio_final, cantidad)
        total_neto_acumulado += subtotal

        # Guardar detalle
        DetalleDocumento.objects.create(
            documento=documento,
            articulo_id=articulo_id,
            cantidad=cantidad,
            precio_unitario_base=precio_base,
            descuento_1_porcentaje=d1,
            descuento_2_porcentaje=d2,
            descuento_3_porcentaje=d3,
            precio_unitario_final=precio_final,
            subtotal_linea=subtotal
        )

        # 3. Bloquear y actualizar el artículo (con select_for_update para prevenir race conditions)
        articulo = Articulo.objects.select_for_update().get(pk=articulo_id)
        stock_anterior = articulo.stock_actual

        if es_nota_credito:
            # Nota de crédito descuenta stock
            if stock_anterior < cantidad:
                raise ValidationError(
                    f"Stock insuficiente para aplicar Nota de Crédito en '{articulo.nombre}'. "
                    f"Stock actual: {stock_anterior}, requerido: {cantidad}"
                )
            nuevo_stock = stock_anterior - cantidad
            tipo_mov = MovimientoInventario.TIPO_SALIDA
            glosa = f"Nota de Crédito N° {documento.numero_documento} - {documento.proveedor.razon_social}"
        else:
            # Entrada normal por Factura, Boleta o Guía
            nuevo_stock = stock_anterior + cantidad
            tipo_mov = MovimientoInventario.TIPO_ENTRADA
            glosa = f"{documento.get_tipo_documento_display()} N° {documento.numero_documento} - {documento.proveedor.razon_social}"

            # Actualizar precios de compra y PMP (Precio Medio Ponderado)
            articulo.ultimo_costo_compra = precio_final
            if nuevo_stock > 0:
                costo_anterior_total = Decimal(str(stock_anterior)) * Decimal(str(articulo.pmp_costo_actual))
                costo_nuevo_total = cantidad * Decimal(str(precio_final))
                pmp_calculado = (costo_anterior_total + costo_nuevo_total) / Decimal(str(nuevo_stock))
                articulo.pmp_costo_actual = int(pmp_calculado.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            else:
                articulo.pmp_costo_actual = precio_final

        articulo.stock_actual = nuevo_stock
        articulo.save()

        # 4. Registrar en MovimientoInventario (log de auditoría)
        MovimientoInventario.objects.create(
            articulo=articulo,
            documento=documento,
            tipo_movimiento=tipo_mov,
            cantidad=cantidad,
            stock_anterior=stock_anterior,
            stock_posterior=nuevo_stock,
            costo_unitario=precio_final,
            usuario=usuario,
            referencia=glosa
        )

    # Actualizar monto total en el documento
    documento.monto_neto = total_neto_acumulado
    documento.save(update_fields=['monto_neto'])

    return documento

