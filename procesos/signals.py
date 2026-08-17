from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Perfil, ProcesoSeleccion


@receiver(pre_save, sender=User)
def proteger_accesos_esenciales(sender, instance, **kwargs):
    """Evita desactivar las cuentas que mantienen operativo el sistema."""
    if kwargs.get("raw"):
        return
    if not instance.pk:
        return
    rol = Perfil.objects.filter(usuario_id=instance.pk).values_list("rol", flat=True).first()
    if rol in (Perfil.Rol.GERENTE, Perfil.Rol.CONTRATACION):
        instance.is_active = True


@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created:
        Perfil.objects.create(usuario=instance)


@receiver(post_save, sender=ProcesoSeleccion)
def iniciar_control_de_tiempo(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created:
        instance.abrir_seguimiento(instance.etapa_actual, instance.creado_en)
