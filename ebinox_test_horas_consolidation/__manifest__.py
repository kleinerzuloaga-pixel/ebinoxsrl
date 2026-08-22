{
    "name": "Ebinox - Consolidación de Jornadas",
    "summary": "Agrupa snapshots privados en jornadas operativas auditables",
    "category": "Human Resources/Attendances",
    "license": "LGPL-3",
    "author": "Ebinox",
    "version": "19.0.1.0.0",
    "depends": ["ebinox_test_horas_calculation"],
    "data": [
        "security/ir.model.access.csv",
        "security/consolidation_security.xml",
        "views/consolidation_run_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}

