from django.contrib.auth import views as auth_views
from django.urls import include, path

from procesos.auth_views import LoginSeguroView
from procesos.views import salud

urlpatterns = [
    path("salud/", salud, name="salud"),
    path("ingresar/", LoginSeguroView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("procesos.urls")),
]
