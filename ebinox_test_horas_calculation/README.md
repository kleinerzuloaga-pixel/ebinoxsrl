# Puente de cálculo Test de Horas

Addon opcional para ejecutar el motor puro sobre `test.horas.workday`.

- No consulta ni escribe `hr.attendance`.
- No publica en Ausencias, Entradas de trabajo ni Nómina.
- Convierte las marcas UTC a la zona horaria guardada antes de calcular.
- Conserva un snapshot JSON y SHA-256 de cada entrada de cálculo.
- Separa exceso detectado de horas liquidables.
- Las extras son no autorizadas por defecto.
- Permite seleccionar explícitamente las políticas aún pendientes con RRHH.
- Puede tomar un snapshot simple de `resource.calendar` o usar horas manuales.

El snapshot automático usa el primer y último tramo laborable del calendario del
día. Calendarios partidos, rotativos o nocturnos complejos deben validarse en
staging antes de habilitarlo como fuente automática.

