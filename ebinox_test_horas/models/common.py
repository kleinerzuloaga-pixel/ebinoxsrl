import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..staging_guard import is_allowed_staging_database


class StagingGuardMixin(models.AbstractModel):
    _name = "test.horas.staging.guard.mixin"
    _description = "Protección de entorno para Test de Horas"

    @api.model
    def _assert_staging(self):
        database = self.env.cr.dbname
        if not is_allowed_staging_database(database):
            raise UserError(
                _(
                    "Operación bloqueada: la base %(database)s no pertenece a la "
                    "lista de staging autorizados."
                ),
                database=database,
            )
        return True

    def _log_test_horas_event(self, action, summary, payload=None):
        self.ensure_one()
        self._assert_staging()
        company = getattr(self, "company_id", False) or self.env.company
        material = payload or {}
        payload_json = json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        )
        return self.env["test.horas.audit.event"].with_context(
            test_horas_audit_internal=True
        ).create(
            {
                "company_id": company.id,
                "action": action,
                "source_model": self._name,
                "source_record_id": self.id,
                "source_display_name": self.display_name,
                "summary": summary,
                "payload_json": payload_json,
                "payload_sha256": hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            }
        )


class ImmutableAuditMixin(models.AbstractModel):
    _name = "test.horas.immutable.audit.mixin"
    _description = "Evidencia inmutable de Test de Horas"

    def unlink(self):
        raise UserError(_("La evidencia de fichadas y auditoría no puede eliminarse."))

    def _raise_immutable(self):
        raise UserError(_("Este registro es evidencia inmutable y no puede modificarse."))


def validate_date_range(start, end, label="período"):
    if start and end and end < start:
        raise ValidationError(_("La fecha final del %(label)s no puede ser anterior a la inicial.", label=label))

