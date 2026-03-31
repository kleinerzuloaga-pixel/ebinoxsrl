# -*- coding: utf-8 -*-
# from odoo import http


# class ExeStockPickingCustom(http.Controller):
#     @http.route('/exe_stock_picking_custom/exe_stock_picking_custom', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/exe_stock_picking_custom/exe_stock_picking_custom/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('exe_stock_picking_custom.listing', {
#             'root': '/exe_stock_picking_custom/exe_stock_picking_custom',
#             'objects': http.request.env['exe_stock_picking_custom.exe_stock_picking_custom'].search([]),
#         })

#     @http.route('/exe_stock_picking_custom/exe_stock_picking_custom/objects/<model("exe_stock_picking_custom.exe_stock_picking_custom"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('exe_stock_picking_custom.object', {
#             'object': obj
#         })
