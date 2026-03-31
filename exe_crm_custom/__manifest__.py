{
    "name": "CRM Customizaciones",
    "summary": """
        Customizaciones en el modulo de CRM""",
    "category": "Administration",
    'version': '19.0.1.0.0',
    "author": "Fabian Cerchi - Exemax",
    "license": "LGPL-3",
    "depends": [
        "base",
        "crm"
    ],
    "data": [
        'views/crm_lead_form_inherit.xml',
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
