from django.test import TestCase

from followup.forms import PatientForm
from followup.models import Patient


class PatientFormTests(TestCase):
    def test_outpatient_number_accepts_blank(self):
        form = PatientForm(
            data={
                "name": "张三",
                "outpatient_number": "",
                "gender": "male",
                "birth_date": "",
                "ethnicity": "",
                "phone": "",
                "address": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_outpatient_number_rejects_invalid_format(self):
        form = PatientForm(
            data={
                "name": "李四",
                "outpatient_number": "ABC123",
                "gender": "female",
                "birth_date": "",
                "ethnicity": "",
                "phone": "",
                "address": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("outpatient_number", form.errors)

    def test_outpatient_number_rejects_duplicate(self):
        Patient.objects.create(
            name="王五",
            gender="male",
            outpatient_number="20260416001",
        )
        form = PatientForm(
            data={
                "name": "赵六",
                "outpatient_number": "20260416001",
                "gender": "other",
                "birth_date": "",
                "ethnicity": "",
                "phone": "",
                "address": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("outpatient_number", form.errors)
