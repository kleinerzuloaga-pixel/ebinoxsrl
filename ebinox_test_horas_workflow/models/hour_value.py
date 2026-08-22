import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class TestHorasHourValue(models.Model):
    _name = "test.horas.hour.value"
    _description = "Valor hora privado y versionado"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "valid_from desc, employee_id, id desc"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    employee_id = fields.Many2one(
        "hr.employee", required=True, index=True, ondelete="restrict",
        domain="[('company_id', '=', company_id)]",
    )
    identification_snapshot = fields.Char(readonly=True, index=True)
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", store=True, readonly=True
    )
    hourly_value = fields.Monetary(required=True, currency_field="currency_id")
    source = fields.Char(required=True, help="Planilla, consultora o responsable que informó el valor.")
    source_reference = fields.Char(required=True, help="Referencia auditable del archivo o comunicación.")
    valid_from = fields.Date(required=True, index=True)
    valid_to = fields.Date(index=True)
    active = fields.Boolean(default=True, index=True)
    notes = fields.Text()

    _sql_constraints = [
        (
            "employee_company_start_unique",
            "unique(employee_id, company_id, valid_from)",
            "Ya existe un valor hora para esa persona, compañía y fecha inicial.",
        ),
        ("hourly_value_positive", "check(hourly_value > 0)", "El valor hora debe ser positivo."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        prepared = []
        employees = self.env["hr.employee"].browse(
            [values.get("employee_id") for values in vals_list if values.get("employee_id")]
        )
        by_id = {employee.id: employee for employee in employees}
        for values in vals_list:
            values = dict(values)
            employee = by_id.get(values.get("employee_id"))
            if employee:
                values.setdefault("company_id", employee.company_id.id)
                values["identification_snapshot"] = employee.identification_id or ""
            prepared.append(values)
        return super().create(prepared)

    def write(self, vals):
        protected = {
            "company_id", "employee_id", "hourly_value", "source", "source_reference",
            "valid_from", "valid_to",
        }
        if protected.intersection(vals):
            used = self.env["test.horas.overtime.valuation"].search_count(
                [("hour_value_id", "in", self.ids)]
            )
            if used:
                raise UserError(
                    _("Un valor hora ya utilizado no se modifica; cierre su vigencia y cree una versión nueva.")
                )
        return super().write(vals)

    @api.constrains("employee_id", "company_id")
    def _check_employee_company(self):
        for record in self:
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(_("La persona y el valor hora deben pertenecer a la misma compañía."))

    @api.constrains("valid_from", "valid_to")
    def _check_dates_and_overlap(self):
        for record in self:
            if record.valid_to and record.valid_to < record.valid_from:
                raise ValidationError(_("La vigencia final no puede ser anterior a la inicial."))
            if not record.employee_id or not record.company_id or not record.valid_from:
                continue
            domain = [
                ("id", "!=", record.id),
                ("employee_id", "=", record.employee_id.id),
                ("company_id", "=", record.company_id.id),
                ("active", "=", True),
                "|", ("valid_to", "=", False), ("valid_to", ">=", record.valid_from),
            ]
            if record.valid_to:
                domain.append(("valid_from", "<=", record.valid_to))
            if self.search_count(domain):
                raise ValidationError(_("La vigencia se superpone con otro valor hora activo."))


class TestHorasOvertimeValuationHourValue(models.Model):
    _inherit = "test.horas.overtime.valuation"

    source_hour_value = fields.Monetary(
        required=True, default=0.0, currency_field="currency_id"
    )
    hour_value_id = fields.Many2one(
        "test.horas.hour.value", readonly=True, ondelete="restrict", copy=False
    )
    manual_source_reference = fields.Char(
        help="Obligatoria si se valoriza con un importe manual sin registro de tarifa vigente."
    )
    hour_value_source_snapshot = fields.Text(readonly=True, copy=False)

    def action_resolve_hour_value(self):
        for valuation in self:
            valuation._assert_staging()
            candidates = self.env["test.horas.hour.value"].search(
                [
                    ("employee_id", "=", valuation.employee_id.id),
                    ("company_id", "=", valuation.company_id.id),
                    ("active", "=", True),
                    ("valid_from", "<=", valuation.valuation_date),
                    "|", ("valid_to", "=", False), ("valid_to", ">=", valuation.valuation_date),
                ],
                order="valid_from desc, id desc",
            )
            if len(candidates) != 1:
                raise ValidationError(
                    _(
                        "Se esperaba un único valor hora vigente para %(employee)s y se encontraron %(count)s.",
                        employee=valuation.employee_id.name,
                        count=len(candidates),
                    )
                )
            tariff = candidates[0]
            snapshot = {
                "hour_value_id": tariff.id,
                "employee_id": tariff.employee_id.id,
                "identification_snapshot": tariff.identification_snapshot,
                "company_id": tariff.company_id.id,
                "hourly_value": tariff.hourly_value,
                "currency": tariff.currency_id.name,
                "source": tariff.source,
                "source_reference": tariff.source_reference,
                "valid_from": fields.Date.to_string(tariff.valid_from),
                "valid_to": fields.Date.to_string(tariff.valid_to) if tariff.valid_to else None,
            }
            valuation.write(
                {
                    "hour_value_id": tariff.id,
                    "source_hour_value": tariff.hourly_value,
                    "manual_source_reference": False,
                    "hour_value_source_snapshot": json.dumps(
                        snapshot, sort_keys=True, ensure_ascii=False
                    ),
                }
            )
        return True

    def action_compute_valuation(self):
        for valuation in self:
            if not valuation.hour_value_id:
                if valuation.source_hour_value:
                    if not valuation.manual_source_reference:
                        raise ValidationError(
                            _("Un valor hora manual requiere una referencia de origen.")
                        )
                    valuation.hour_value_source_snapshot = json.dumps(
                        {
                            "mode": "manual",
                            "source_hour_value": valuation.source_hour_value,
                            "source_reference": valuation.manual_source_reference,
                            "valuation_date": fields.Date.to_string(valuation.valuation_date),
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                else:
                    valuation.action_resolve_hour_value()
            elif valuation.source_hour_value != valuation.hour_value_id.hourly_value:
                raise ValidationError(_("El valor aplicado no coincide con la tarifa vinculada."))
        return super().action_compute_valuation()
