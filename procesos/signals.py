from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Perfil, ProcesoSeleccion


@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.create(usuario=instance)


@receiver(post_save, sender=ProcesoSeleccion)
def iniciar_control_de_tiempo(sender, instance, created, **kwargs):
    if created:
        instance.abrir_seguimiento(instance.etapa_actual, instance.creado_en)
