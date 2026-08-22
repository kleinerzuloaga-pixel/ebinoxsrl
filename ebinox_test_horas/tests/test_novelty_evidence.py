import base64
import hashlib
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestNoveltyEvidence(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")
        employee = cls.env["hr.employee"].create(
            {"name": "Empleado evidencia", "company_id": cls.env.company.id}
        )
        novelty_type = cls.env["test.horas.novelty.type"].create(
            {"code": "EVTEST", "name": "Evidencia test"}
        )
        cls.novelty = cls.env["test.horas.daily.novelty"].create(
            {
                "employee_id": employee.id,
                "date": date(2026, 8, 3),
                "novelty_type_id": novelty_type.id,
                "reason": "Respaldo obligatorio",
            }
        )

    def test_binary_is_private_hashed_and_immutable(self):
        raw = b"documento privado de prueba"
        attachment_count = self.env["ir.attachment"].search_count([])
        evidence = self.env["test.horas.novelty.evidence"].create(
            {
                "novelty_id": self.novelty.id,
                "file_name": "respaldo.txt",
                "mime_type": "text/plain",
                "file_data": base64.b64encode(raw),
                "note": "Documento de prueba no productivo",
            }
        )
        self.assertEqual(evidence.file_size, len(raw))
        self.assertEqual(evidence.content_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.env["ir.attachment"].search_count([]), attachment_count)
        with self.assertRaises(UserError):
            evidence.note = "No se puede reemplazar"
        with self.assertRaises(UserError):
            evidence.unlink()
