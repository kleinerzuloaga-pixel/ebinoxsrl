# Ebinox - Novedades y Horas

Addon piloto para trasladar Test de Horas exclusivamente a Odoo staging.

La instalación y las operaciones fallan si la base no coincide con
`ebinox-staging-` seguido de un número de build de Odoo.sh. La base
productiva `ebinox` queda bloqueada. No se usa una lista de un solo build:
un rebuild de staging no exige cambiar código.
