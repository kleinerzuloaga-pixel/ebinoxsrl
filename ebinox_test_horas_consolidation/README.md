# Consolidación privada de jornadas

Este addon agrupa `test.horas.clock.event` por empleado y fecha operativa para
crear o actualizar `test.horas.workday`.

- Sólo lee asignación de calendario desde `hr.employee`/`resource.calendar`.
- No usa `sudo`, cron ni operaciones de escritura sobre modelos estándar.
- Ignora versiones anteriores de un mismo evento de `hr.attendance`.
- Reconstruye turnos simples y turnos partidos 22–24 / 00–06.
- Conserva una marca de horario no resuelto en vez de inventar uno.
- No modifica jornadas cerradas.
- Si cambia evidencia de una jornada procesada, la devuelve a revisión.
- La ejecución es manual, por compañía y con ventana máxima de 62 días.

Calendarios de dos semanas, rotaciones o excepciones complejas deben validarse
en Odoo staging antes de considerarse resueltos automáticamente.

