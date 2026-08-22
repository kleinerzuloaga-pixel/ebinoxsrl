from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class TestHorasAuditEvent(models.Model):
    _name = "test.horas.audit.event"
    _description = "Evento transversal inmutable de Test de Horas"
    _inherit = [
        "test.horas.staging.guard.mixin",
        "test.horas.immutable.audit.mixin",
    ]
    _order = "occurred_at desc, id desc"

    company_id = fields.Many2one("res.company", required=True, index=True, ondelete="restrict")
    action = fields.Char(required=True, index=True)
    source_model = fields.Char(required=True, index=True)
    source_record_id = fields.Integer(required=True, index=True)
    source_display_name = fields.Char(required=True)
    summary = fields.Text(required=True)
    payload_json = fields.Text(readonly=True)
    payload_sha256 = fields.Char(required=True, readonly=True, index=True)
    occurred_at = fields.Datetime(
        required=True, readonly=True, default=fields.Datetime.now, index=True
    )
    actor_id = fields.Many2one(
        "res.users", required=True, readonly=True, default=lambda self: self.env.user, index=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        if not self.env.context.get("test_horas_audit_internal"):
            raise AccessError(_("Los eventos de auditoría sólo pueden generarse desde procesos internos."))
        return super().create(vals_list)

    def write(self, vals):
        self._raise_immutable()

