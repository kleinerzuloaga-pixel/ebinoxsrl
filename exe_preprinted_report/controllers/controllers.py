# -*- coding: utf-8 -*-
# from odoo import http


# class ExePreprintedReport(http.Controller):
#     @http.route('/exe_preprinted_report/exe_preprinted_report', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/exe_preprinted_report/exe_preprinted_report/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('exe_preprinted_report.listing', {
#             'root': '/exe_preprinted_report/exe_preprinted_report',
#             'objects': http.request.env['exe_preprinted_report.exe_preprinted_report'].search([]),
#         })

#     @http.route('/exe_preprinted_report/exe_preprinted_report/objects/<model("exe_preprinted_report.exe_preprinted_report"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('exe_preprinted_report.object', {
#             'object': obj
#         })
