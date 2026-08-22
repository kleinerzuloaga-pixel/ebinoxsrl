from odoo import models


class TestHorasTransitionExportValuationSource(models.Model):
    _inherit = "test.horas.transition.export"

    def _generate_valuation(self):
        headers, rows, source_ids = super()._generate_valuation()
        insert_at = headers.index("source_hour_value") + 1
        headers[insert_at:insert_at] = [
            "hour_value_id",
            "hour_value_mode",
            "hour_value_source",
            "hour_value_source_reference",
            "hour_value_valid_from",
            "hour_value_valid_to",
            "manual_source_reference",
            "hour_value_source_snapshot",
        ]
        valuations = self.env["test.horas.overtime.valuation"].search(
            [("period_id", "=", self.period_id.id)], order="employee_id, id"
        )
        for row, valuation in zip(rows, valuations):
            tariff = valuation.hour_value_id
            source_values = [
                tariff.id or "",
                "tariff" if tariff else "manual",
                tariff.source or "",
                tariff.source_reference or "",
                tariff.valid_from or "",
                tariff.valid_to or "",
                valuation.manual_source_reference or "",
                valuation.hour_value_source_snapshot or "",
            ]
            row[insert_at:insert_at] = source_values
        source_ids["hour_value_ids"] = valuations.mapped("hour_value_id").ids
        return headers, rows, source_ids
