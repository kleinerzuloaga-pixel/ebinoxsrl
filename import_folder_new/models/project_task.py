# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import models, fields, api, exceptions, _
from odoo.exceptions import UserError
import logging
_logger= logging.getLogger(__name__)

class ProjectTaskInherit(models.Model):
    _inherit = 'project.task'

    purchase_order_ids = fields.One2many('purchase.order','task_id', string='Pedidos de compras')
    stock_picking_ids = fields.One2many('stock.picking','task_id', string='Remitos')
    invoice_ids = fields.One2many('account.move','task_id', string='Facturas proveedor')
    invoice_ids_filtered = fields.Many2many('account.move', 'task_id', string='Facturas proveedor')
    purchase_count = fields.Integer(compute='_compute_task_data_purchase', string="Pedidos de compras")
    invoice_count = fields.Integer(store=True,readonly=False)
    #stock_count_import = fields.Integer(string='Cantidad de Remitos', compute='_compute_stock_count', store=True)
    stock_count_i = fields.Integer(compute='_compute_task_data_stock', string="Remitos")
    is_import = fields.Boolean(string="Es Importación")
    tags_import = fields.Many2many('project.tags', string="Categorías", relation='project_task_tags_import_rel')
    importation = fields.Boolean(related='project_id.importation', string='Importación', store=True)
    invoice_numbers = fields.Char(string='Número de Factura', compute='_compute_invoice_ids')
    supplier = fields.Many2one('res.partner', string='Proveedor')
    instructor_id = fields.Many2one('res.partner', string='Agente de carga')
    dispatch = fields.Char(string='Nro Despacho')
    import_license = fields.Char(string='Licencia de importación')
    divisa = fields.Many2one('res.currency', string='Divisa',domain="[('active', '=', True)]")
    ncm = fields.Char(string='NCM')
    shipping = fields.Selection([('mar','Marítimo'),('air','Aéreo'),('ground','Terrestre'),],string='Embarque')
    incoterm = fields.Char(string='INCOTERM')
    etd = fields.Date(string='ETD')
    eta = fields.Date(string='ETA/Arribo')
    closing_date = fields.Date(string='Fecha de cierre de importación')
    tipo_bl = fields.Selection([
        ('guia', 'Guía'),
        ('bl', 'BL'),
        ('crt', 'CRT')
    ], string='Tipo Doc de Transporte', default='')
 

class ImportCampos(models.Model):
    _inherit = 'project.task'

    operation = fields.Char('Referencia proveedor')
    arrive = fields.Char('Arribo')
    inal = fields.Selection([('requiere', 'Requiere'),('no requiere', 'No requiere')], string='INAL/MARCA')
    bl = fields.Char('Nro Doc Transporte')
    sira_aprob = fields.Selection([('si', 'Si'),('no', 'No')], string='SEDI aprobado')
    sira_text = fields.Char(string='SEDI')
    sira_date = fields.Date('Vencimiento SEDI')
    mulc_date = fields.Date('MULC')
    nav = fields.Char('Naviera')
    currency_id = fields.Many2one('res.currency', string="Currency",
                                 related='company_id.currency_id',
                                 default=lambda
                                 self: self.env.user.company_id.currency_id.id)
    for_money = fields.Monetary(string="FOB R")
    sira_money = fields.Monetary(string="FOB SEDI")
    currency_field = fields.Many2one('res.currency', string='Divisas')
    traslation = fields.Selection([('si', 'Si'),('no', 'No')], string='Traslada')

#Solapa CUENTAS
    bank = fields.Many2one('res.bank', string='Banco nominado')
    ant_fob = fields.Monetary(string="Anticipo FOB")
    sal_fob = fields.Monetary(string="Saldo FOB")
    sal_ofi = fields.Monetary(string="Monto oficializacón")
    sal_ter = fields.Monetary(string="Monto terminal")
    sal_nav = fields.Monetary(string="Monto naviera")
    nav_date = fields.Date('Fecha naviera')
    fob_cancel = fields.Selection([('si', 'Si'),('no', 'No')], string='FOB Cancelado')


    total_moneda = fields.Monetary(
       string='Total Moneda',
       compute='_compute_total_moneda'
    )

    @api.depends('sira_money', 'sal_ofi', 'sal_ter', 'sal_nav')
    def _compute_total_moneda(self):
        for record in self:
            record.total_moneda = (
                record.sira_money + record.sal_ofi + record.sal_ter + record.sal_nav
            )

#Solapa CANALES
    inc = fields.Float('INC')
    online = fields.Float('Online')
    ret = fields.Float('Retail')
    may = fields.Float('Mayorista')

#Solapa LOGÍSTICA
    website_link = fields.Char('Enlace al sitio web')
    number_cont = fields.Char('Nro. de contenedor')
    weight = fields.Integer('Peso bruto')
    ret_cont = fields.Char('Retiro contenedor')
    term_arrive = fields.Char('Terminal arribo')
    term_dev = fields.Char('Terminal devolución')
    venc = fields.Date('Vencimiemto libre deuda')
    ctr = fields.Integer('cant. CTR')
    desc = fields.Selection([('si', 'Si'),('no', 'No')], string='Desconsolida')
    dep_fisc = fields.Char('Deposito fiscal')

    def _compute_invoice_ids(self):
        for rec in self:
            invoices = self.env['account.move'].search([('task_id','=',rec.id), ('l10n_latam_document_type_id.doc_code_prefix', 'in', ['FA-I', 'DI'])]) #MODIFICAR SEGUN EL CLIENTE (Y LOS CODIGOS QUE UTILICE)
            if invoices:
                for invoice in invoices:
                    if rec.invoice_numbers:
                        rec.invoice_numbers = str(rec.invoice_numbers) + ', '+ invoice.name
                    else:
                        rec.invoice_numbers = invoice.name
            else:
                rec.invoice_numbers = ''


    def _compute_income_invoice_check(self):
        for rec in self:
            if any(sale.tag_ids.filtered(lambda tag: tag.name == 'Ingresos') for sale in rec.sale_order_id):
                rec.income_invoice_check = True
            else:
                rec.income_invoice_check = False


    def _compute_discharge_invoice_check(self):
        for rec in self:
            if any(sale.tag_ids.filtered(lambda tag: tag.name == 'Egresos') for sale in rec.sale_order_id):
                rec.discharge_invoice_check = True
            else:
                rec.discharge_invoice_check = False


    @api.onchange('is_import')
    def _onchange_is_import(self):
        if self.is_import:
            return {'domain': {'tags_import': [('is_import', '=', True)]}}
        else:
            self.tags_import = [(5, 0, 0)]
            return {'domain': {'tags_import': []}}


    @api.onchange('project_id')
    def _onchange_project_id_import(self):
        if self.project_id:
           self.is_import = self.project_id.importation
           if self.is_import:
           # Si es importación, mostrar solo etiquetas con is_import=True
               return {'domain': {'tags_import': [('is_import', '=', True)]}}
           else:
               # Si no es importación, mostrar solo etiquetas con is_import=False
               return {'domain': {'tags_import': [('is_import', '=', False)]}}
        else:
           # Si no hay proyecto seleccionado, limpiar el campo y eliminar el dominio
            self.is_import = False
            self.tags_import = [(5, 0, 0)]
            return {'domain': {'tags_import': []}}




    @api.depends('purchase_order_ids')
    def _compute_task_data_purchase(self):
        for rec in self:
            purchase_ids = self.env['purchase.order'].search([('task_id', 'in', rec.id)])
            rec.purchase_count = len(purchase_ids)
            invoices_filtered = self.env['account.move'].search([('task_id', 'in', rec.id)])
            rec.invoice_ids_filtered = [(6, 0, invoices_filtered.ids)]
            rec.invoice_count = len(invoices_filtered)

    '''@api.depends('task_ids')
    def _compute_stock_count(self):
        for rec in self:
            # Contar los remitos que tienen esta tarea asociada
            stock_pickings = self.env['stock.picking'].search_count([('task_ids', 'in', rec.id)])
            rec.stock_count = stock_pickings'''

    @api.depends('stock_picking_ids')
    def _compute_task_data_stock(self):
        for rec in self:
            sp_cnt = self.env['stock.picking'].search_count([('task_ids', '=', rec.id)])
            rec.stock_count_i = sp_cnt


    @api.depends('project_id')
    def get_value_project(self):
        for rec in self:
            rec.importation_task = rec.project_id.importation
            return rec.importation_task

    def action_view_project_stock(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("import_folder_new.stock_picking_action_list_view")
        action['domain'] = [('task_ids', '=', self.id)]
        return action

    def action_view_project_account(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("import_folder_new.account_move_action_list_view")
        action['domain'] = [('id', 'in', self.invoice_ids_filtered.ids)]
        return action

    def action_view_project_purchase(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("import_folder_new.purchase_order_action_list_view")
        action['domain'] = [('task_id', '=', self.id)]
        return action

 
