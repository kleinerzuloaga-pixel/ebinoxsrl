# -*- coding: utf-8 -*-
{
    'name': "Account Move Custom Rate",

    'summary': """
        Take the custom rate for calculate amount other currency """,

    'description': """
        Take the custom rate for calculate amount other currency
    """,

    'author': "Exemax, Gabriela Riquelme",
    'website': "http://www.Exemax.com.ar",
    'license': 'AGPL-3',
    'category': 'Account',
    'version': '0.1',

    'depends': ['l10n_latam_invoice_document', 'l10n_latam_base',],

    'data': [
        'views/views.xml'
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
