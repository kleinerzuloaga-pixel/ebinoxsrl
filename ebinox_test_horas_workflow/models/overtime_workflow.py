import hashlib
import json
from decimal import Decimal, ROUND_CEILING

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


VALUATION_VERSION = "2026-08-21.valoracion.v1"


class TestHorasOvertimePeriodWorkflow(models.Model):
    _inherit = "test.horas.overtime.period"

    authorization_input_hash = fields.Char(readonly=True, index=True)
    authorization_snapshot = fields.Text(readonly=True)

    @api.constrains("company_id", "date_from", "date_to", "state")
    def _check_non_overlapping_periods(self):
        for record in self:
            if not record.company_id or not record.date_from or not record.date_to:
                continue
            overlap = self.search_count(
                [
                    ("id", "!=", record.id),
                    ("company_id", "=", record.company_id.id),
                    ("state", "!=", "cancelled"),
                    ("date_from", "<=", record.date_to),
                    ("date_to", ">=", record.date_from),
                ]
            )
            if overlap:
                raise ValidationError(_("El período se superpone con otro período activo de la compañía."))

    def action_generate_lines(self):
        for period in self:
            period._assert_staging()
            if period.state not in {"draft", "calculated"}:
                raise UserError(_("Sólo se regeneran líneas en períodos borrador o calculados."))
            workdays = self.env["test.horas.workday"].search(
                [
                    ("company_id", "=", period.company_id.id),
                    ("operational_date", ">=", period.date_from),
                    ("operational_date", "<=", period.date_to),
                    ("state", "in", ["calculated", "audited"]),
                    ("detected_overtime_min", ">", 0),
                ],
                order="operational_date, employee_id",
            )
            existing = {line.workday_id.id: line for line in period.line_ids}
            selected_ids = set()
            for workday in workdays:
                selected_ids.add(workday.id)
                values = period._line_values_from_workday(workday)
                line = existing.get(workday.id)
                if line:
                    line.write(values)
                else:
                    values.update({"period_id": period.id, "workday_id": workday.id})
                    self.env["test.horas.overtime.line"].create(values)
            for line in period.line_ids.filtered(lambda item: item.workday_id.id not in selected_ids):
                line.active = False
            period.write(
                {"state": "calculated", "calculation_version": "2026-08-21.odoo19.v2.multisegment"}
            )
        return True

    def action_submit(self):
        for period in self:
            if period.state != "calculated":
                raise ValidationError(_("El período debe estar calculado antes de enviarlo."))
        return super().action_submit()

    def action_approve(self):
        for period in self:
            period._assert_staging()
            if period.state != "submitted":
                raise ValidationError(_("Sólo puede autorizarse un período presentado."))
            if not period.approval_reason:
                raise ValidationError(_("La autorización requiere un motivo o referencia."))
            if not self.env.user.has_group("ebinox_test_horas.group_test_horas_supervisor"):
                raise ValidationError(_("Sólo un supervisor puede autorizar horas extra."))
            for line in period.line_ids.filtered("active"):
                if line.excluded and not line.exclusion_reason:
                    raise ValidationError(
                        _("Toda exclusión diaria requiere un motivo: %s.", line.display_name)
                    )
                workday = line.workday_id
                workday.write(
                    {
                        "overtime_authorized": True,
                        "overtime_excluded": line.excluded,
                        "overtime_exclusion_reason": line.exclusion_reason or False,
                    }
                )
                workday.action_calculate_test_horas()
                line.write(period._line_values_from_workday(workday))
            snapshot = period._authorization_snapshot_values()
            encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            period.write(
                {
                    "authorization_snapshot": json.dumps(snapshot, sort_keys=True, ensure_ascii=False),
                    "authorization_input_hash": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
                }
            )
        result = super().action_approve()
        for period in self:
            period._log_test_horas_event(
                "overtime.approved",
                "Período de horas extra autorizado",
                {
                    "date_from": period.date_from,
                    "date_to": period.date_to,
                    "authorization_hash": period.authorization_input_hash,
                    "line_count": len(period.line_ids),
                },
            )
        return result

    def action_mark_valued(self):
        for period in self:
            if period.state != "approved":
                raise ValidationError(_("Sólo puede valorizarse un período autorizado."))
            employee_ids = set(
                period.line_ids.filtered(
                    lambda line: line.active
                    and not line.excluded
                    and (
                        line.payable_50_diurnal_min
                        + line.payable_50_nocturnal_min
                        + line.payable_100_diurnal_min
                        + line.payable_100_nocturnal_min
                    )
                    > 0
                ).mapped("employee_id").ids
            )
            valued_ids = set(
                self.env["test.horas.overtime.valuation"].search(
                    [("period_id", "=", period.id), ("state", "!=", "not_applicable")]
                ).mapped("employee_id").ids
            )
            missing = employee_ids - valued_ids
            if missing:
                raise ValidationError(_("Faltan valorizaciones para %s empleados.", len(missing)))
            period.state = "valued"
        return True

    def _line_values_from_workday(self, workday):
        return {
            "employee_id": workday.employee_id.id,
            "date": workday.operational_date,
            "active": True,
            "detected_excess_min": workday.detected_overtime_min,
            "raw_50_diurnal_min": workday.raw_50_diurnal_min,
            "raw_50_nocturnal_min": workday.raw_50_nocturnal_min,
            "raw_100_diurnal_min": workday.raw_100_diurnal_min,
            "raw_100_nocturnal_min": workday.raw_100_nocturnal_min,
            "payable_50_diurnal_min": workday.payable_50_diurnal_min,
            "payable_50_nocturnal_min": workday.payable_50_nocturnal_min,
            "payable_100_diurnal_min": workday.payable_100_diurnal_min,
            "payable_100_nocturnal_min": workday.payable_100_nocturnal_min,
        }

    def _authorization_snapshot_values(self):
        self.ensure_one()
        return {
            "period_id": self.id,
            "company_id": self.company_id.id,
            "date_from": fields.Date.to_string(self.date_from),
            "date_to": fields.Date.to_string(self.date_to),
            "approval_reason": self.approval_reason,
            "lines": [
                {
                    "line_id": line.id,
                    "workday_id": line.workday_id.id,
                    "employee_id": line.employee_id.id,
                    "date": fields.Date.to_string(line.date),
                    "detected_excess_min": line.detected_excess_min,
                    "excluded": line.excluded,
                    "exclusion_reason": line.exclusion_reason or None,
                }
                for line in self.line_ids.filtered("active").sorted(key=lambda item: (item.date, item.id))
            ],
        }


class TestHorasOvertimeLineWorkflow(models.Model):
    _inherit = "test.horas.overtime.line"

    active = fields.Boolean(default=True, index=True)
    raw_50_diurnal_min = fields.Integer(readonly=True)
    raw_50_nocturnal_min = fields.Integer(readonly=True)
    raw_100_diurnal_min = fields.Integer(readonly=True)
    raw_100_nocturnal_min = fields.Integer(readonly=True)

    @api.constrains("excluded", "exclusion_reason")
    def _check_exclusion_reason(self):
        for line in self:
            if line.excluded and not line.exclusion_reason:
                raise ValidationError(_("Una exclusión diaria requiere motivo."))


class TestHorasOvertimeValuationWorkflow(models.Model):
    _inherit = "test.horas.overtime.valuation"

    amount_50_diurnal = fields.Monetary(currency_field="currency_id", readonly=True)
    amount_50_nocturnal = fields.Monetary(currency_field="currency_id", readonly=True)
    amount_100_diurnal = fields.Monetary(currency_field="currency_id", readonly=True)
    amount_100_nocturnal = fields.Monetary(currency_field="currency_id", readonly=True)
    valuation_input_hash = fields.Char(readonly=True, index=True)
    valuation_snapshot = fields.Text(readonly=True)

    def action_compute_valuation(self):
        for valuation in self:
            valuation._assert_staging()
            if valuation.period_id.state not in {"approved", "valued"}:
                raise ValidationError(_("El período debe estar autorizado antes de valorizar."))
            lines = valuation.period_id.line_ids.filtered(
                lambda line: line.active and line.employee_id == valuation.employee_id and not line.excluded
            )
            if not lines:
                raise ValidationError(_("No hay horas extra autorizadas para la persona en el período."))
            minutes = {
                "50_diurnal": sum(lines.mapped("payable_50_diurnal_min")),
                "50_nocturnal": sum(lines.mapped("payable_50_nocturnal_min")),
                "100_diurnal": sum(lines.mapped("payable_100_diurnal_min")),
                "100_nocturnal": sum(lines.mapped("payable_100_nocturnal_min")),
            }
            base = Decimal(str(valuation.source_hour_value)) * Decimal(str(valuation.base_factor))
            factor_50 = Decimal(str(valuation.overtime_50_factor))
            factor_100 = Decimal(str(valuation.overtime_100_factor))
            night = Decimal("1") + Decimal(str(valuation.nocturnal_factor))
            amounts = {
                "50_diurnal": Decimal(minutes["50_diurnal"]) / Decimal("60") * base * factor_50,
                "50_nocturnal": Decimal(minutes["50_nocturnal"]) / Decimal("60") * base * factor_50 * night,
                "100_diurnal": Decimal(minutes["100_diurnal"]) / Decimal("60") * base * factor_100,
                "100_nocturnal": Decimal(minutes["100_nocturnal"]) / Decimal("60") * base * factor_100 * night,
            }
            raw = sum(amounts.values(), Decimal("0"))
            rounded = (raw / Decimal("100")).to_integral_value(rounding=ROUND_CEILING) * Decimal("100")
            snapshot = {
                "version": VALUATION_VERSION,
                "valuation_id": valuation.id,
                "period_id": valuation.period_id.id,
                "employee_id": valuation.employee_id.id,
                "minutes": minutes,
                "source_hour_value": str(valuation.source_hour_value),
                "base_factor": str(valuation.base_factor),
                "overtime_50_factor": str(valuation.overtime_50_factor),
                "overtime_100_factor": str(valuation.overtime_100_factor),
                "nocturnal_factor": str(valuation.nocturnal_factor),
                "raw_amount": str(raw),
                "rounded_amount": str(rounded),
            }
            encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            valuation.write(
                {
                    "amount_50_diurnal": float(amounts["50_diurnal"]),
                    "amount_50_nocturnal": float(amounts["50_nocturnal"]),
                    "amount_100_diurnal": float(amounts["100_diurnal"]),
                    "amount_100_nocturnal": float(amounts["100_nocturnal"]),
                    "raw_amount": float(raw),
                    "rounded_amount": float(rounded),
                    "rule_version": VALUATION_VERSION,
                    "valuation_snapshot": json.dumps(snapshot, sort_keys=True, ensure_ascii=False),
                    "valuation_input_hash": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
                    "state": "prepared",
                }
            )
            valuation._log_test_horas_event(
                "valuation.computed",
                "Valorización de horas extra calculada",
                {
                    "period_id": valuation.period_id.id,
                    "input_hash": valuation.valuation_input_hash,
                    "rounded_amount": valuation.rounded_amount,
                    "currency_id": valuation.currency_id.id,
                },
            )
        return True

    def action_mark_paid(self):
        for valuation in self:
            if not valuation.payment_reference:
                raise ValidationError(_("Para marcar Pago se requiere una referencia de pago."))
            valuation.state = "paid"
            valuation._log_test_horas_event(
                "valuation.paid",
                "Valorización marcada como pagada",
                {"payment_reference": valuation.payment_reference, "rounded_amount": valuation.rounded_amount},
            )
        return True

    def action_mark_pending(self):
        self.write({"state": "pending"})
        for valuation in self:
            valuation._log_test_horas_event(
                "valuation.pending",
                "Valorización marcada pendiente",
                {"rounded_amount": valuation.rounded_amount},
            )
        return True

