{
    "name": "Ebinox - Exportaciones de Transición Test de Horas",
    "summary": "CSV comparables NOV, NOVCAL, EXTRAS y valorización",
    "category": "Human Resources/Attendances",
    "license": "LGPL-3",
    "author": "Ebinox",
    "version": "19.0.1.0.0",
    "depends": ["ebinox_test_horas_reporting"],
    "data": [
        "security/ir.model.access.csv",
        "security/export_security.xml",
        "views/transition_export_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}

