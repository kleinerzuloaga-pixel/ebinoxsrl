import base64
import binascii
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


MAX_EVIDENCE_BYTES = 10 * 1024 * 1024


class TestHorasDailyNoveltyEvidenceRelation(models.Model):
    _inherit = "test.horas.daily.novelty"

    evidence_ids = fields.One2many(
        "test.horas.novelty.evidence", "novelty_id", string="Evidencia privada"
    )


class TestHorasNoveltyEvidence(models.Model):
    _name = "test.horas.novelty.evidence"
    _description = "Evidencia privada e inmutable de novedad"
    _inherit = ["test.horas.staging.guard.mixin", "test.horas.immutable.audit.mixin"]
    _order = "uploaded_at desc, id desc"

    novelty_id = fields.Many2one(
        "test.horas.daily.novelty", required=True, index=True, ondelete="restrict"
    )
    employee_id = fields.Many2one(
        related="novelty_id.employee_id", store=True, index=True, readonly=True
    )
    company_id = fields.Many2one(
        related="employee_id.company_id", store=True, index=True, readonly=True
    )
    file_name = fields.Char(required=True)
    mime_type = fields.Char(required=True, default="application/octet-stream")
    file_data = fields.Binary(required=True, attachment=False)
    file_size = fields.Integer(readonly=True)
    content_sha256 = fields.Char(required=True, readonly=True, index=True)
    note = fields.Text(required=True)
    uploaded_by_id = fields.Many2one(
        "res.users", required=True, readonly=True, default=lambda self: self.env.user
    )
    uploaded_at = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)

    _sql_constraints = [
        (
            "novelty_content_unique",
            "unique(novelty_id, content_sha256)",
            "Ese archivo ya fue incorporado como evidencia de la novedad.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        prepared = []
        for vals in vals_list:
            values = dict(vals)
            encoded = values.get("file_data")
            try:
                raw = base64.b64decode(encoded or b"", validate=True)
            except (binascii.Error, TypeError, ValueError) as exc:
                raise ValidationError(_("La evidencia no contiene un archivo base64 válido.")) from exc
            if not raw:
                raise ValidationError(_("La evidencia no puede estar vacía."))
            if len(raw) > MAX_EVIDENCE_BYTES:
                raise ValidationError(_("La evidencia supera el límite de 10 MB."))
            values.update(
                {
                    "file_size": len(raw),
                    "content_sha256": hashlib.sha256(raw).hexdigest(),
                    "uploaded_by_id": self.env.user.id,
                    "uploaded_at": fields.Datetime.now(),
                }
            )
            prepared.append(values)
        return super().create(prepared)
