{
    "name": "Ebinox - Cálculo de Novedades y Horas",
    "summary": "Puente aislado entre jornadas Odoo y el motor Test de Horas",
    "category": "Human Resources/Attendances",
    "license": "LGPL-3",
    "author": "Ebinox",
    "version": "19.0.1.0.0",
    "depends": ["ebinox_test_horas"],
    "data": ["views/workday_calculation_views.xml"],
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}

