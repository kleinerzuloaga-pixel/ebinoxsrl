{
    "name": "Ebinox - Adaptador de Asistencias para Test de Horas",
    "summary": "Lectura aislada e idempotente de hr.attendance para el piloto",
    "category": "Human Resources/Attendances",
    "license": "LGPL-3",
    "author": "Ebinox",
    "version": "19.0.1.0.0",
    "depends": ["ebinox_test_horas", "hr_attendance"],
    "data": [
        "security/ir.model.access.csv",
        "security/attendance_adapter_security.xml",
        "views/attendance_sync_run_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}

