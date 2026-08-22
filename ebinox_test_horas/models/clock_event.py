from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TestHorasClockEvent(models.Model):
    _name = "test.horas.clock.event"
    _description = "Evento crudo de reloj"
    _inherit = ["test.horas.staging.guard.mixin", "test.horas.immutable.audit.mixin"]
    _order = "timestamp desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    timestamp = fields.Datetime(required=True, index=True)
    source = fields.Char(required=True, index=True, help="Sistema que originó la marcación.")
    external_id = fields.Char(required=True, index=True, help="Identificador idempotente en el origen.")
    event_kind = fields.Selection(
        [("unknown", "Sin clasificar"), ("in", "Entrada"), ("out", "Salida")],
        required=True,
        default="unknown",
    )
    source_payload = fields.Text(help="Carga útil mínima para auditoría; no almacenar secretos.")
    imported_at = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    imported_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)

    _sql_constraints = [
        (
            "source_external_unique",
            "unique(source, external_id)",
            "El evento ya fue importado desde ese origen.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("Una marcación cruda no puede sobrescribirse; importe un evento correctivo."))

