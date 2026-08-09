from django.core.management.base import BaseCommand

from procesos.calendario import sumar_dias_habiles
from procesos.models import PLAZOS_ETAPA_DIAS, ProcesoSeleccion, SeguimientoEtapa


class Command(BaseCommand):
    help = "Reconstruye los tiempos de procesos antiguos que todavía no tienen seguimiento"

    def handle(self, *args, **options):
        reconstruidos = 0
        for proceso in ProcesoSeleccion.objects.prefetch_related("decisiones", "seguimientos").all():
            if proceso.seguimientos.exists():
                continue
            inicio = proceso.creado_en
            ciclos = {}
            for decision in proceso.decisiones.filter(vigente=True).order_by("fecha"):
                ciclos[decision.etapa] = ciclos.get(decision.etapa, 0) + 1
                SeguimientoEtapa.objects.create(
                    proceso=proceso,
                    etapa=decision.etapa,
                    ciclo=ciclos[decision.etapa],
                    inicio=inicio,
                    fecha_limite=sumar_dias_habiles(inicio, PLAZOS_ETAPA_DIAS[decision.etapa]),
                    fin=decision.fecha,
                    resultado=decision.resultado,
                    cerrado_por=decision.decidido_por,
                )
                inicio = decision.fecha
            if proceso.activo and not proceso.esta_finalizado:
                ciclos[proceso.etapa_actual] = ciclos.get(proceso.etapa_actual, 0) + 1
                SeguimientoEtapa.objects.create(
                    proceso=proceso,
                    etapa=proceso.etapa_actual,
                    ciclo=ciclos[proceso.etapa_actual],
                    inicio=inicio,
                    fecha_limite=sumar_dias_habiles(inicio, PLAZOS_ETAPA_DIAS[proceso.etapa_actual]),
                )
            reconstruidos += 1
        self.stdout.write(self.style.SUCCESS(f"Procesos reconstruidos: {reconstruidos}"))
