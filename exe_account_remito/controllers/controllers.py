# -*- coding: utf-8 -*-
# from odoo import http


# class ExeAccountRemito(http.Controller):
#     @http.route('/exe_account_remito/exe_account_remito', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/exe_account_remito/exe_account_remito/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('exe_account_remito.listing', {
#             'root': '/exe_account_remito/exe_account_remito',
#             'objects': http.request.env['exe_account_remito.exe_account_remito'].search([]),
#         })

#     @http.route('/exe_account_remito/exe_account_remito/objects/<model("exe_account_remito.exe_account_remito"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('exe_account_remito.object', {
#             'object': obj
#         })
