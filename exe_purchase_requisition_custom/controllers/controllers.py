# -*- coding: utf-8 -*-
# from odoo import http


# class ExePurchaseRequisitionCustom(http.Controller):
#     @http.route('/exe_purchase_requisition_custom/exe_purchase_requisition_custom', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/exe_purchase_requisition_custom/exe_purchase_requisition_custom/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('exe_purchase_requisition_custom.listing', {
#             'root': '/exe_purchase_requisition_custom/exe_purchase_requisition_custom',
#             'objects': http.request.env['exe_purchase_requisition_custom.exe_purchase_requisition_custom'].search([]),
#         })

#     @http.route('/exe_purchase_requisition_custom/exe_purchase_requisition_custom/objects/<model("exe_purchase_requisition_custom.exe_purchase_requisition_custom"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('exe_purchase_requisition_custom.object', {
#             'object': obj
#         })
