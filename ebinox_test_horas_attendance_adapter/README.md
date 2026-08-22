# Adaptador aislado de Asistencias

Este addon opcional depende de `hr_attendance` y del núcleo
`ebinox_test_horas`. Lee asistencias mediante el ORM con los permisos corrientes
del usuario y crea snapshots inmutables en `test.horas.clock.event`.

Propiedades del piloto:

- ejecución exclusivamente manual;
- exige simultáneamente rol funcional del piloto y permiso de administrador de
  Asistencias ya existente;
- no usa `sudo()`;
- no llama `create`, `write` ni `unlink` sobre `hr.attendance`;
- limita cada ventana a 62 días;
- separa compañías;
- genera un identificador idempotente por registro, tipo de evento y timestamp;
- conserva una nueva versión si el origen cambia su entrada o salida;
- no contiene cron ni publicación hacia Ausencias, Entradas de trabajo o Nómina.

