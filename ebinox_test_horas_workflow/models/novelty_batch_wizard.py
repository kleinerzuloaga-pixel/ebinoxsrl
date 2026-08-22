from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


MAX_RANGE_DAYS = 62


class TestHorasNoveltyBatchWizard(models.TransientModel):
    _name = "test.horas.novelty.batch.wizard"
    _description = "Carga masiva aislada de novedades"
    _inherit = ["test.horas.staging.guard.mixin"]

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Personas",
        required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    novelty_type_id = fields.Many2one(
        "test.horas.novelty.type",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    reason = fields.Text(required=True)
    document_reference = fields.Char()
    monday = fields.Boolean(default=True)
    tuesday = fields.Boolean(default=True)
    wednesday = fields.Boolean(default=True)
    thursday = fields.Boolean(default=True)
    friday = fields.Boolean(default=True)
    saturday = fields.Boolean(default=True)
    sunday = fields.Boolean(default=True)
    submit_created = fields.Boolean(
        string="Presentar las novedades creadas",
        help="No aprueba: conserva la segregación y deja la aprobación al supervisor.",
    )
    state = fields.Selection(
        [("draft", "Borrador"), ("done", "Generado")], default="draft", readonly=True
    )
    created_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
    operations_log = fields.Text(readonly=True)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to:
                if record.date_to < record.date_from:
                    raise ValidationError(_("La fecha final no puede ser anterior a la inicial."))
                if (record.date_to - record.date_from).days + 1 > MAX_RANGE_DAYS:
                    raise ValidationError(
                        _("La carga masiva admite como máximo %s días.", MAX_RANGE_DAYS)
                    )

    @api.constrains("novelty_type_id", "company_id")
    def _check_novelty_company(self):
        for record in self:
            if (
                record.novelty_type_id.company_id
                and record.novelty_type_id.company_id != record.company_id
            ):
                raise ValidationError(_("El tipo de novedad pertenece a otra compañía."))

    @api.constrains("employee_ids", "company_id")
    def _check_employee_companies(self):
        for record in self:
            if any(employee.company_id != record.company_id for employee in record.employee_ids):
                raise ValidationError(_("Todas las personas deben pertenecer a la compañía elegida."))

    def action_generate(self):
        self.ensure_one()
        self._assert_staging()
        if self.state != "draft":
            raise UserError(_("Esta carga masiva ya fue ejecutada."))
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_operator"):
            raise UserError(_("Se requiere el rol Operador RRHH de Test de Horas."))

        weekdays = {
            index
            for index, selected in enumerate(
                (
                    self.monday,
                    self.tuesday,
                    self.wednesday,
                    self.thursday,
                    self.friday,
                    self.saturday,
                    self.sunday,
                )
            )
            if selected
        }
        if not weekdays:
            raise ValidationError(_("Seleccione al menos un día de la semana."))

        selected_dates = []
        cursor = self.date_from
        while cursor <= self.date_to:
            if cursor.weekday() in weekdays:
                selected_dates.append(cursor)
            cursor += timedelta(days=1)

        novelty_model = self.env["test.horas.daily.novelty"]
        existing = novelty_model.search(
            [
                ("employee_id", "in", self.employee_ids.ids),
                ("date", "in", selected_dates),
            ]
        )
        existing_keys = {(item.employee_id.id, item.date) for item in existing}
        values = []
        skipped = 0
        for employee in self.employee_ids.sorted(key=lambda item: item.id):
            for selected_date in selected_dates:
                if (employee.id, selected_date) in existing_keys:
                    skipped += 1
                    continue
                values.append(
                    {
                        "employee_id": employee.id,
                        "date": selected_date,
                        "novelty_type_id": self.novelty_type_id.id,
                        "reason": self.reason,
                        "document_reference": self.document_reference or False,
                    }
                )

        created = novelty_model.create(values) if values else novelty_model.browse()
        if self.submit_created:
            created.action_submit()
        self.write(
            {
                "state": "done",
                "created_count": len(created),
                "skipped_count": skipped,
                "operations_log": _(
                    "Creadas: %(created)s. Omitidas por existencia previa: %(skipped)s. "
                    "Escrituras estándar: 0.",
                    created=len(created),
                    skipped=skipped,
                ),
            }
        )
        if not created:
            return True
        return {
            "type": "ir.actions.act_window",
            "name": _("Novedades generadas"),
            "res_model": "test.horas.daily.novelty",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }
