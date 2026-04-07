# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import models, fields, api, exceptions, _
import logging

# Configura el logger para registrar mensajes de depuración y errores
_logger = logging.getLogger(__name__)

# Define una nueva clase que hereda del modelo 'account.move'
class AccountMoveInherit(models.Model):
    _inherit = 'account.move'
     
    
    # Define un campo Many2many para asociar varias tareas de proyecto a un movimiento contable
    task_id = fields.Many2many('project.task', string='Carpeta de importación', readonly=False)
    
# Define una nueva clase que hereda del modelo 'account.move.line'
class AccountMoveInheritLine(models.Model):
    _inherit = 'account.move.line'

    # Define un campo Many2one para asociar una orden de venta con una línea de movimiento contable
    sale_id = fields.Many2one('sale.order', string='Sale Order', compute='_compute_sale_id')

    # Método para calcular el valor del campo 'sale_id'
    def _compute_sale_id(self):
        for rec in self:
            # Si la línea de movimiento tiene líneas de venta asociadas
            if rec.sale_line_ids:
                # Asigna la orden de venta correspondiente al campo 'sale_id'
                rec.sale_id = rec.sale_line_ids.order_id.id
            else:
                # Si no hay líneas de venta, asigna False
                rec.sale_id = False

