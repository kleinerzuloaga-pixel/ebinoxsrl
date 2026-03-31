from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    purchase_order_ids = fields.One2many('purchase.order', 'sale_order_id', string='Presupuestos de Compra')

    def action_create_purchase_order(self):
        for order in self:
            # Buscar un proveedor con un ranking mayor a 0
            vendor_id = self.env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
            if not vendor_id:
                raise ValidationError('No hay un proveedor definido para crear el presupuesto de compra.')
            
            purchase_order = self.env['purchase.order'].create({
                'origin': order.name,
                'partner_id': vendor_id.id,  # Establecer el proveedor
                'order_line': [(0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'product_qty': line.product_uom_qty,
                    'product_uom_id': line.product_uom_id.id,
                    'price_unit': line.price_unit,  #  precio unitario
                    'price_subtotal': line.price_subtotal,  # subtotal
                }) for line in order.order_line]
            })
            order.purchase_order_ids = [(4, purchase_order.id)]
            return { 'type': 'ir.actions.act_window', 'name': 'Presupuesto de Compra', 'view_mode': 'form', 'res_model': 'purchase.order', 'res_id': purchase_order.id, 'target': 'current',}

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    sale_order_id = fields.Many2one('sale.order', string='Pedido de Venta Origen')

