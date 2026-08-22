# Exportaciones de transición

Genera CSV UTF-8 con BOM y separador `;` para comparación controlada:

- NOV detalle diario;
- NOVCAL calendario persona × día;
- NOV resumen diagnóstico por quincena;
- EXTRAS con buckets crudos/liquidables y autorización;
- Valorización con factores, componentes, importes y referencias;
- cierres mensuales.

El archivo binario usa `attachment=False`: permanece en la tabla privada del
modelo y no crea `ir.attachment`. Cada salida es inmutable, conserva IDs fuente
y SHA-256, y está rotulada como diagnóstica. No se escribe ni importa nada en
módulos estándar.

