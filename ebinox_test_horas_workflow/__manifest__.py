{
    "name": "Ebinox - Flujo de Novedades, Extras y Valorización",
    "summary": "Aprobación y valorización aisladas para Test de Horas",
    "category": "Human Resources/Attendances",
    "license": "LGPL-3",
    "author": "Ebinox",
    "version": "19.0.1.0.0",
    "depends": ["ebinox_test_horas_calculation"],
    "data": [
        "security/ir.model.access.csv",
        "security/novelty_batch_security.xml",
        "security/hour_value_security.xml",
        "data/novelty_types.xml",
        "views/novelty_workflow_views.xml",
        "views/novelty_batch_wizard_views.xml",
        "views/overtime_workflow_views.xml",
        "views/hour_value_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}

