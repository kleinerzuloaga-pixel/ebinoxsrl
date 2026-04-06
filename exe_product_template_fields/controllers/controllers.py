# -*- coding: utf-8 -*-
# from odoo import http


# class ExeProductTemplateFields(http.Controller):
#     @http.route('/exe_product_template_fields/exe_product_template_fields', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/exe_product_template_fields/exe_product_template_fields/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('exe_product_template_fields.listing', {
#             'root': '/exe_product_template_fields/exe_product_template_fields',
#             'objects': http.request.env['exe_product_template_fields.exe_product_template_fields'].search([]),
#         })

#     @http.route('/exe_product_template_fields/exe_product_template_fields/objects/<model("exe_product_template_fields.exe_product_template_fields"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('exe_product_template_fields.object', {
#             'object': obj
#         })
