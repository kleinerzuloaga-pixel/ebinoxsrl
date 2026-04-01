# -*- coding: utf-8 -*-
# from odoo import http


# class ExeFleetVehicle(http.Controller):
#     @http.route('/exe_fleet_vehicle/exe_fleet_vehicle', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/exe_fleet_vehicle/exe_fleet_vehicle/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('exe_fleet_vehicle.listing', {
#             'root': '/exe_fleet_vehicle/exe_fleet_vehicle',
#             'objects': http.request.env['exe_fleet_vehicle.exe_fleet_vehicle'].search([]),
#         })

#     @http.route('/exe_fleet_vehicle/exe_fleet_vehicle/objects/<model("exe_fleet_vehicle.exe_fleet_vehicle"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('exe_fleet_vehicle.object', {
#             'object': obj
#         })
