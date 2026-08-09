from django.urls import path

from . import views

app_name = "procesos"

urlpatterns = [
    path("", views.lista_procesos, name="lista"),
    path("contratacion/", views.lista_contratacion, name="contratacion"),
    path("rechazados/", views.lista_rechazados, name="rechazados"),
    path("archivados/", views.lista_archivados, name="archivados"),
    path("trazabilidad/", views.trazabilidad, name="trazabilidad"),
    path("nuevo/", views.crear_proceso, name="crear"),
    path("candidato/<int:pk>/", views.detalle_proceso, name="detalle"),
    path("candidato/<int:pk>/editar/", views.editar_proceso_gerencia, name="proceso_editar"),
    path("candidato/<int:pk>/actividad/", views.cambiar_actividad_proceso, name="proceso_actividad"),
    path("usuarios/", views.lista_usuarios, name="usuarios"),
    path("auditoria-seguridad/", views.auditoria_seguridad, name="auditoria_seguridad"),
    path("usuarios/nuevo/", views.crear_usuario, name="usuario_crear"),
    path("usuarios/<int:pk>/editar/", views.editar_usuario, name="usuario_editar"),
    path("usuarios/<int:pk>/password/", views.cambiar_password_usuario, name="usuario_password"),
]
