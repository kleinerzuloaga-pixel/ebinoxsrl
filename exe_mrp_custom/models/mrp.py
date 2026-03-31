# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

class MrpWorkorderInherit(models.Model):
    _inherit = 'mrp.workorder'

    duration_expected_hours = fields.Float(string='Duración esperada Horas', digits=(16, 2),)

    duration_hours = fields.Float(string='Duración real Horas', digits=(16, 2), compute='_compute_duration_hours')

    @api.onchange('duration_expected_hours')
    def onchange_duration_hours(self):
        for rec in self:
            if rec.duration_expected_hours:
                rec.duration_expected = rec.duration_expected_hours * 60

    @api.depends('duration')   
    def _compute_duration_hours(self):
        for rec in self:
            if rec.duration:
                rec.duration_hours = rec.duration / 60
            else:
                rec.duration_hours = 0.0


class MrpWProductivityInherit(models.Model):
    _inherit = 'mrp.workcenter.productivity'

    duration_hours = fields.Float(string='Duración real Horas', digits=(16, 2), compute='_compute_duration_hours')

    @api.depends('duration')    
    def _compute_duration_hours(self):
        for rec in self:
            if rec.duration:
                rec.duration_hours = rec.duration / 60
            else:
                rec.duration_hours = 0.0

class MrpRWorkcenterInherit(models.Model):
    _inherit = 'mrp.routing.workcenter'

    time_cycle_hours = fields.Float(string='Duración (Horas)', digits=(16, 2), compute='_compute_time_cycle_hours')

    @api.depends('time_cycle')    
    def _compute_time_cycle_hours(self):
        for rec in self:
            if rec.time_cycle:
                rec.time_cycle_hours = rec.time_cycle / 60
            else:
                rec.time_cycle_hours = 0.0
           