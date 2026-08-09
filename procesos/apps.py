from django.apps import AppConfig


class ProcesosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "procesos"

    def ready(self):
        import procesos.signals  # noqa: F401
