from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # inverse field of the one created on payment groups, used by other modules
    # like sipreco
    payment_group_ids = fields.Many2many(
        'account.payment.group',
        'account_move_line_payment_group_to_pay_rel',
        'to_pay_line_id',
        'payment_group_id',
        string="Grupos de Pago",
        readonly=True,
        # auto_join not yet implemented for m2m. TODO enable when implemented
        # https://github.com/odoo/odoo/blob/master/odoo/osv/expression.py#L899
        # auto_join=True,
    )

    @api.model
    def _create_exchange_difference_move(self, exchange_diff_vals):
        """ Create the exchange difference journal entry on the current journal items.
        :param exchange_diff_vals:  The current vals of the exchange difference journal entry created by the
                                    '_prepare_exchange_difference_move_vals' method.
        :return:                    An account.move record.
        """
        return

    def reconcile(self):
        ''' Reconcile the current move lines all together.
        :return: A dictionary representing a summary of what has been done during the reconciliation:
                * partials:             A recorset of all account.partial.reconcile created during the reconciliation.
                * exchange_partials:    A recorset of all account.partial.reconcile created during the reconciliation
                                        with the exchange difference journal entries.
                * full_reconcile:       An account.full.reconcile record created when there is nothing left to reconcile
                                        in the involved lines.
                * tax_cash_basis_moves: An account.move recordset representing the tax cash basis journal entries.
        '''
        results = {'exchange_partials': self.env['account.partial.reconcile']}

        if not self:
            return results

        not_paid_invoices = self.move_id.filtered(lambda move:
            move.is_invoice(include_receipts=True)
            and move.payment_state not in ('paid', 'in_payment')
        )

        # ==== Check the lines can be reconciled together ====
        company = None
        account = None
        for line in self:
            if line.reconciled:
                raise UserError(_("You are trying to reconcile some entries that are already reconciled."))
            if not line.account_id.reconcile and line.account_id.account_type not in ('asset_cash', 'liability_credit_card'):
                raise UserError(_("Account %s does not allow reconciliation. First change the configuration of this account to allow it.")
                                % line.account_id.display_name)
            if line.move_id.state != 'posted':
                raise UserError(_('You can only reconcile posted entries.'))
            if company is None:
                company = line.company_id
            elif line.company_id != company:
                raise UserError(_("Entries doesn't belong to the same company: %s != %s")
                                % (company.display_name, line.company_id.display_name))
            if account is None:
                account = line.account_id
            elif line.account_id != account:
                raise UserError(_("Entries are not from the same account: %s != %s")
                                % (account.display_name, line.account_id.display_name))

        if self._context.get('reduced_line_sorting'):
            sorting_f = lambda line: (line.date_maturity or line.date, line.currency_id)
        else:
            sorting_f = lambda line: (line.date_maturity or line.date, line.currency_id, line.amount_currency)
        sorted_lines = self.sorted(key=sorting_f)

        # ==== Collect all involved lines through the existing reconciliation ====

        involved_lines = sorted_lines._all_reconciled_lines()
        involved_partials = involved_lines.matched_credit_ids | involved_lines.matched_debit_ids

        # ==== Create partials ====

        partial_no_exch_diff = bool(self.env['ir.config_parameter'].sudo().get_param('account.disable_partial_exchange_diff'))
        sorted_lines_ctx = sorted_lines.with_context(no_exchange_difference=self._context.get('no_exchange_difference') or partial_no_exch_diff)
        partials = sorted_lines_ctx._create_reconciliation_partials()
        results['partials'] = partials
        involved_partials += partials
        exchange_move_lines = partials.exchange_move_id.line_ids.filtered(lambda line: line.account_id == account)
        involved_lines += exchange_move_lines
        exchange_diff_partials = exchange_move_lines.matched_debit_ids + exchange_move_lines.matched_credit_ids
        involved_partials += exchange_diff_partials
        results['exchange_partials'] += exchange_diff_partials

        # ==== Create entries for cash basis taxes ====

        is_cash_basis_needed = account.company_id.tax_exigibility and account.account_type in ('asset_receivable', 'liability_payable')
        if is_cash_basis_needed and not self._context.get('move_reverse_cancel') and not self._context.get('no_cash_basis'):
            tax_cash_basis_moves = partials._create_tax_cash_basis_moves()
            results['tax_cash_basis_moves'] = tax_cash_basis_moves

        # ==== Check if a full reconcile is needed ====

        def is_line_reconciled(line, has_multiple_currencies):
            # Check if the journal item passed as parameter is now fully reconciled.
            return line.reconciled \
                   or (line.company_currency_id.is_zero(line.amount_residual)
                       if has_multiple_currencies
                       else line.currency_id.is_zero(line.amount_residual_currency)
                   )

        has_multiple_currencies = len(involved_lines.currency_id) > 1
        if all(is_line_reconciled(line, has_multiple_currencies) for line in involved_lines):
            # ==== Create the exchange difference move ====
            # This part could be bypassed using the 'no_exchange_difference' key inside the context. This is useful
            # when importing a full accounting including the reconciliation like Winbooks.

            exchange_move = self.env['account.move']
            caba_lines_to_reconcile = None

            # === Cash basis rounding autoreconciliation ===
            # In case a cash basis rounding difference line got created for the transition account, we reconcile it with the corresponding lines
            # on the cash basis moves (so that it reaches full reconciliation and creates an exchange difference entry for this account as well)

            if caba_lines_to_reconcile:
                for (dummy, account, repartition_line), amls_to_reconcile in caba_lines_to_reconcile.items():
                    if not account.reconcile:
                        continue

                    exchange_line = exchange_move.line_ids.filtered(
                        lambda l: l.account_id == account and l.tax_repartition_line_id == repartition_line
                    )

                    (exchange_line + amls_to_reconcile).filtered(lambda l: not l.reconciled).reconcile()

        not_paid_invoices.filtered(lambda move:
            move.payment_state in ('paid', 'in_payment')
        )._invoice_paid_hook()

        return results

    def _compute_payment_group_matched_amount(self):
        """
        Recibir un payment_group_id por contexto, decimos en ese payment
        group, cuanto se pago para la lína en cuestión.
        """
        payment_group_id = self._context.get('payment_group_id')
        if not payment_group_id:
            return False
        payments = self.env['account.payment.group'].browse(
            payment_group_id).payment_ids
        # payment_move_lines = payments.mapped('move_line_ids')
        payment_move_lines = payments.mapped('invoice_line_ids')

        for rec in self:
            matched_amount = 0.0
            reconciles = self.env['account.partial.reconcile'].search([
                ('credit_move_id', 'in', payment_move_lines.ids),
                ('debit_move_id', '=', rec.id)])
            matched_amount += sum(reconciles.mapped('amount'))

            reconciles = self.env['account.partial.reconcile'].search([
                ('debit_move_id', 'in', payment_move_lines.ids),
                ('credit_move_id', '=', rec.id)])
            matched_amount -= sum(reconciles.mapped('amount'))
            rec.payment_group_matched_amount = matched_amount

    payment_group_matched_amount = fields.Monetary(
        compute='_compute_payment_group_matched_amount',
        currency_field='company_currency_id',
    )
