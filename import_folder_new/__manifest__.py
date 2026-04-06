{
    "name": "Carpeta de Importaciones",
    'version': '15.0',
    'author': "Exemax (Brenda Gauto) / Israel Perez - EXEMAX / Gabriel / Irene Colichelli",
    'website': "http://www.exemax.com.ar",
    'category': 'Project',
    'version': '15.0.1',
    'depends': [
        'base',
        'project',
        'stock',
        'purchase',
        'account',
        'purchase_stock',
        'sale',
        'stock_account',
        'account_payment_group'
    ],
    'installable': True,
    'license': 'AGPL-3',
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/account_move.xml',
        'views/project_project.xml',
        'views/project_task.xml',
        'views/purchase_order.xml',
        'views/stock.xml',
        'views/dispatch.xml',
        'views/project_tags_view.xml',
        
    ],
     
}
