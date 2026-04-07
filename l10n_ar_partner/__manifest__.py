{
    'name': 'Datos Extras para Contacto de Argentina',
    'version': '16.0.0.1.0',
    'category': 'Partner',
    'license': 'AGPL-3',
    'summary': "Datos Extras para Contacto de Argentina",
    'description': """
Datos Extras para Contacto de Argentina
=======================================

* Agrega nombre de Fantasía
    """,
    'author': 'Codize, Exemax',
    'website': 'http://www.codize.ar',
    # 'depends': ['base'],
    'depends': [
        'base', 
        'l10n_latam_base', 
        'l10n_ar',
        'mail', # Added because the error triggers during mail data load
    ],
    'data': ['partner_view.xml'],
    'installable': True,
}
