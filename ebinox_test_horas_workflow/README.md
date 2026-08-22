# Flujo aislado de novedades, extras y valorización

Este addon conecta exclusivamente modelos `test.horas.*`:

1. Una novedad aprobada se aplica a una jornada privada o crea una jornada sin
   marcas; nunca crea `hr.leave`.
2. Un período genera líneas desde jornadas calculadas con exceso detectado.
3. La autorización explícita recalcula las jornadas y transforma los buckets
   crudos en liquidables, respetando exclusiones diarias con motivo.
4. La valorización aplica los factores versionados y redondea hacia arriba a
   centenas, guardando snapshot y hash.

No hay cron, `sudo`, asientos contables, pagos reales, entradas de trabajo ni
conceptos de nómina. Los estados Pago/Pendiente son sólo estados del prototipo.

