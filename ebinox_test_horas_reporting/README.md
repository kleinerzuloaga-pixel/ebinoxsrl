# Reportes y cierres aislados

Este addon agrega perfiles auxiliares, feriados propios, ausentismo, tardanzas y
cierres mensuales sin extender ni escribir modelos operativos estándar.

- Universo: directos, indirectos o todos los perfiles activos.
- Ausencias: AI, AJ, E, ART, L, LS, V y S.
- Día esperado sin marcas/novedad: AI.
- Evento de tardanza para ranking: más de 5 minutos.
- Porcentaje: días-persona ausentes / días-persona esperados incluidos.
- Altas con menos de 5 días hábiles al cierre: quedan en detalle pero se
  excluyen del numerador y denominador.
- Semana: lunes como inicio.
- Corridas y cierres guardan hashes y no se recalculan destruyendo resultados.

Los perfiles se pueden preparar leyendo empleados activos, pero tipo de
dotación, fecha de ingreso y convenio permanecen snapshots propios que RRHH debe
clasificar/validar.

