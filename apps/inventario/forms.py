from django import forms
from .models import DocumentoEntrada
from apps.entidades.models import Proveedor

class DocumentoEntradaForm(forms.ModelForm):
    class Meta:
        model = DocumentoEntrada
        fields = [
            'proveedor',
            'tipo_documento',
            'numero_documento',
            'fecha_emision',
            'observaciones'
        ]
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select select2', 'required': 'required'}),
            'tipo_documento': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'numero_documento': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: F-98234', 'required': 'required'}),
            'fecha_emision': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': 'required'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Notas u observaciones del ingreso'}),
        }

