from odoo import api, fields, models, SUPERUSER_ID
from collections import defaultdict
from contextlib import ExitStack, contextmanager
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from hashlib import sha256
from json import dumps
import re
from textwrap import shorten
from unittest.mock import patch
from odoo.exceptions import AccessError, UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = "account.move"

    #@api.model
    def write(self, values):
        res = super(AccountMove, self).write(values)
        for rec in self:
            rec.sudo().with_context(check_move_validity=False, check_amount_currency_balance_sign=False).manual_rate()
        return res

    @api.model
    def create(self, values):
        res = super(AccountMove, self).create(values)
        for rec in self:
            rec.sudo().with_context(check_move_validity=False, check_amount_currency_balance_sign=False).manual_rate()
        return res

    def manual_rate(self):
        for line in self.line_ids:
            if self.es_manual_rate == True:
                if line.debit > 0:
                    line.debit = abs(line.amount_currency) * self.currency_rate
                if line.credit > 0:
                    line.credit = abs(line.amount_currency) * self.currency_rate

    @api.depends('currency_id')
    def _get_currency_rate(self):
        for record in self:
            rate = 1
            if record.es_manual_rate==False:
                if record.currency_id.rate > 0:
                    if record.currency_id.name != 'ARS':
                        rate = 1 / record.currency_id.rate
                    else:
                        rate = 1
                    record.currency_rate = rate

    @contextmanager
    def _check_balanced(self, container):
        #if self.move_type == 'in_invoice' or self.move_type == 'in_refund' or self.move_type == 'entry':
        #    if self.es_manual_rate==True:
        #        return True
        with self._disable_recursion(container, 'check_move_validity', default=True, target=False) as disabled:
            yield
            if disabled:
                return

        for move in self:
            if move.move_type == 'in_invoice' or move.move_type == 'in_refund' or move.move_type == 'entry':
                if move.es_manual_rate==True:
                    return True

        unbalanced_moves = self._get_unbalanced_moves(container)
        if unbalanced_moves:
            error_msg = "An error has occurred."
            for move_id, sum_debit, sum_credit in unbalanced_moves:
                move = self.browse(move_id)
                #error_msg += _(
                #    "\n\n"
                #    "The move (%s) is not balanced.\n"
                #    "The total of debits equals %s and the total of credits equals %s.\n"
                #    "You might want to specify a default account on journal \"%s\" to automatically balance each move.",
                #    move.display_name,
                #    format_amount(self.env, sum_debit, move.company_id.currency_id),
                #    format_amount(self.env, sum_credit, move.company_id.currency_id),
                #    move.journal_id.name)
            raise UserError(error_msg)

    currency_rate = fields.Float(string='Tasa de cambio', readonly=False ,compute='_get_currency_rate', store=True)
    es_manual_rate = fields.Boolean(string='Usar TC manual')
