import json
import re
import time
from datetime import timedelta

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Sum
from django.utils import timezone

from .models import (
    ClinicalTerm,
    FollowUp,
    Patient,
    ProjectEnrollment,
    PrescriptionItem,
    PrescriptionTemplate,
    PrescriptionTemplateItem,
    ResearchProject,
    ScaleRecord,
    ScaleTemplate,
    ScaleTemplateItem,
    Treatment,
    UserProfile,
)

_FORM_CACHE_TTL_SECONDS = 180
_FORM_CACHE_MAX_ITEMS = 8
_SCALE_TEMPLATE_PAYLOAD_CACHE = {}
_PRESCRIPTION_TEMPLATE_PAYLOAD_CACHE = {}


def _cache_get(bucket, key):
    now = time.monotonic()
    item = bucket.get(key)
    if not item:
        return None
    if item["expires_at"] <= now:
        bucket.pop(key, None)
        return None
    return item["value"]


def _cache_set(bucket, key, value):
    now = time.monotonic()
    if len(bucket) >= _FORM_CACHE_MAX_ITEMS:
        expired_keys = [item_key for item_key, item in bucket.items() if item["expires_at"] <= now]
        for item_key in expired_keys:
            bucket.pop(item_key, None)
        if len(bucket) >= _FORM_CACHE_MAX_ITEMS:
            oldest_key = min(bucket, key=lambda item_key: bucket[item_key]["expires_at"])
            bucket.pop(oldest_key, None)
    bucket[key] = {"expires_at": now + _FORM_CACHE_TTL_SECONDS, "value": value}


def _scale_template_signature():
    template_agg = ScaleTemplate.objects.aggregate(
        total=Count("id"),
        active_total=Sum("is_active"),
        max_id=Max("id"),
    )
    item_agg = ScaleTemplateItem.objects.aggregate(
        total=Count("id"),
        max_id=Max("id"),
    )
    return (
        template_agg.get("total") or 0,
        int(template_agg.get("active_total") or 0),
        template_agg.get("max_id") or 0,
        item_agg.get("total") or 0,
        item_agg.get("max_id") or 0,
    )


def _prescription_template_signature():
    template_agg = PrescriptionTemplate.objects.aggregate(
        total=Count("id"),
        active_total=Sum("is_active"),
        max_id=Max("id"),
    )
    item_agg = PrescriptionTemplateItem.objects.aggregate(
        total=Count("id"),
        max_id=Max("id"),
    )
    return (
        template_agg.get("total") or 0,
        int(template_agg.get("active_total") or 0),
        template_agg.get("max_id") or 0,
        item_agg.get("total") or 0,
        item_agg.get("max_id") or 0,
    )


class DateInput(forms.DateInput):
    input_type = "text"

    def __init__(self, attrs=None, format="%Y-%m-%d"):
        attrs = attrs or {}
        existing_class = attrs.pop("class", "")
        merged_attrs = {
            "lang": "zh-CN",
            "autocomplete": "off",
            "data-date-input": "true",
            "data-flatpickr": "date",
            "placeholder": "YYYY-MM-DD",
            "class": " ".join(filter(None, [existing_class, "js-date-input"])),
        }
        merged_attrs.update(attrs)
        super().__init__(attrs=merged_attrs, format=format)


def _parse_scale_options(options_text):
    return [item.strip() for item in (options_text or "").split(",") if item.strip()]


def _normalize_scale_key(value, fallback):
    text = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", (value or "").strip()).strip("_")
    return text or fallback


def _build_scale_templates_payload():
    cache_key = ("scale_templates_payload", _scale_template_signature())
    cached = _cache_get(_SCALE_TEMPLATE_PAYLOAD_CACHE, cache_key)
    if cached is not None:
        return cached
    payload = []
    for template in ScaleTemplate.objects.filter(is_active=True).prefetch_related("items"):
        items = list(template.items.all())
        sections = []
        section_map = {}
        default_section = {"key": "__default__", "title": "未分组条目", "description": "", "items": []}
        question_items = []
        for index, item in enumerate(items, start=1):
            item_key = item.item_key or _normalize_scale_key(item.label, f"item_{index}")
            if item.field_type == ScaleTemplateItem.FIELD_GROUP:
                section_key = item.group_key or item_key
                section = {
                    "key": section_key,
                    "title": item.label,
                    "description": item.help_text,
                    "items": [],
                }
                sections.append(section)
                section_map[section_key] = section
                continue
            row = {
                "key": item_key,
                "group_key": item.group_key,
                "parent_key": item.parent_key,
                "label": item.label,
                "field_type": item.field_type,
                "help_text": item.help_text,
                "score_min": item.score_min,
                "score_max": item.score_max,
                "options": _parse_scale_options(item.options_text),
            }
            question_items.append(row)
            if item.group_key and item.group_key in section_map:
                section_map[item.group_key]["items"].append(row)
            else:
                default_section["items"].append(row)
        if default_section["items"]:
            sections.append(default_section)
        payload.append(
            {
                "id": template.pk,
                "name": template.name,
                "description": template.description,
                "sections": sections,
                "items": question_items,
            }
        )
    _cache_set(_SCALE_TEMPLATE_PAYLOAD_CACHE, cache_key, payload)
    return payload


def _build_prescription_templates_payload():
    cache_key = ("prescription_templates_payload", _prescription_template_signature())
    cached = _cache_get(_PRESCRIPTION_TEMPLATE_PAYLOAD_CACHE, cache_key)
    if cached is not None:
        return cached
    active_templates = list(PrescriptionTemplate.objects.filter(is_active=True).order_by("name"))
    template_choices = [("", "")]
    template_choices.extend((str(item.pk), item.name) for item in active_templates)
    templates = []
    detailed_templates = (
        PrescriptionTemplate.objects.filter(is_active=True).prefetch_related("items").order_by("name")
    )
    for template in detailed_templates:
        templates.append(
            {
                "id": template.pk,
                "name": template.name,
                "usage_method": template.usage_method,
                "items": [
                    {
                        "herb_name": item.herb_name,
                        "dosage": item.dosage,
                        "unit": item.unit,
                        "usage": item.usage,
                    }
                    for item in template.items.all()
                ],
            }
        )
    payload = {"choices": template_choices, "templates": templates}
    _cache_set(_PRESCRIPTION_TEMPLATE_PAYLOAD_CACHE, cache_key, payload)
    return payload


def _normalize_scale_records(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return []
    try:
        items = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValidationError("量表数据格式错误，请重新录入。") from exc
    if not isinstance(items, list):
        raise ValidationError("量表数据格式错误，请重新录入。")

    requested_template_ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            template_id = int(item.get("template_id"))
        except (TypeError, ValueError):
            continue
        requested_template_ids.add(template_id)
    valid_templates = {
        template.id: template
        for template in ScaleTemplate.objects.filter(
            is_active=True,
            id__in=requested_template_ids,
        ).prefetch_related("items")
    }
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        template_id = item.get("template_id")
        try:
            template_id = int(template_id)
        except (TypeError, ValueError):
            continue
        template = valid_templates.get(template_id)
        if not template:
            continue

        answers = item.get("answers") or []
        if not isinstance(answers, list):
            answers = []

        normalized_answers = []
        question_items = [
            template_item
            for template_item in template.items.all()
            if template_item.field_type != ScaleTemplateItem.FIELD_GROUP
        ]
        answer_by_key = {}
        sequence_answers = []
        for answer in answers:
            row = answer if isinstance(answer, dict) else {}
            key = (row.get("key") or "").strip()
            if key:
                answer_by_key[key] = row
            sequence_answers.append(row)

        for index, template_item in enumerate(question_items):
            item_key = template_item.item_key or _normalize_scale_key(template_item.label, f"item_{index + 1}")
            answer = answer_by_key.get(item_key)
            if answer is None and index < len(sequence_answers):
                answer = sequence_answers[index]
            answer = answer if isinstance(answer, dict) else {}
            raw_value = answer.get("value", answer.get("score"))
            note = (answer.get("note") or "").strip()

            if template_item.field_type in {
                ScaleTemplateItem.FIELD_SCORE,
                ScaleTemplateItem.FIELD_NUMBER,
            }:
                if raw_value in ("", None):
                    normalized_value = None
                else:
                    try:
                        normalized_value = int(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise ValidationError(f"量表“{template.name}”中的“{template_item.label}”必须填写整数。") from exc
                    if normalized_value < template_item.score_min or normalized_value > template_item.score_max:
                        raise ValidationError(f"量表“{template.name}”中的“{template_item.label}”超出允许范围。")
            elif template_item.field_type == ScaleTemplateItem.FIELD_SELECT:
                normalized_value = (raw_value or "").strip()
                options = _parse_scale_options(template_item.options_text)
                if normalized_value and options and normalized_value not in options:
                    raise ValidationError(f"量表“{template.name}”中的“{template_item.label}”选项无效。")
            else:
                normalized_value = (raw_value or "").strip()

            normalized_answers.append(
                {
                    "key": item_key,
                    "label": template_item.label,
                    "field_type": template_item.field_type,
                    "group_key": template_item.group_key,
                    "parent_key": template_item.parent_key,
                    "value": normalized_value,
                    "note": note,
                }
            )

        cleaned.append(
            {
                "template": template,
                "answers_json": normalized_answers,
                "total_score": None,
                "notes": (item.get("notes") or "").strip(),
            }
        )
    return cleaned


def _replace_prescription_items(treatment, items):
    treatment.prescription_items.all().delete()
    PrescriptionItem.objects.bulk_create(
        [
            PrescriptionItem(
                treatment=treatment,
                herb_name=item["herb_name"],
                dosage=item["dosage"],
                unit=item["unit"],
                usage=item["usage"],
                sort_order=item["sort_order"],
            )
            for item in items
        ]
    )
    treatment.sync_prescription_text()
    treatment.save(update_fields=["prescription"])


def _replace_scale_records(*, treatment=None, followup=None, items=None, actor=None):
    owner_field = "treatment" if treatment is not None else "followup"
    owner = treatment if treatment is not None else followup
    if owner is None:
        return
    owner.scale_records.all().delete()
    ScaleRecord.objects.bulk_create(
        [
            ScaleRecord(
                **{owner_field: owner},
                template=item["template"],
                answers_json=item["answers_json"],
                total_score=item["total_score"],
                notes=item["notes"],
                created_by=actor,
                updated_by=actor,
                updated_at=timezone.now() if actor else None,
            )
            for item in (items or [])
        ]
    )


def _ensure_unique_herb_names(items, *, message_builder):
    seen = {}
    for index, item in enumerate(items, start=1):
        herb_name = (item.get("herb_name") or "").strip()
        normalized = herb_name.lower()
        if not normalized:
            continue
        if normalized in seen:
            raise ValidationError(message_builder(index, herb_name))
        seen[normalized] = index


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ["name", "outpatient_number", "gender", "birth_date", "ethnicity", "phone", "address"]
        widgets = {
            "birth_date": DateInput(),
        }

    def clean_outpatient_number(self):
        value = (self.cleaned_data.get("outpatient_number") or "").strip()
        if not value:
            return ""
        if not re.fullmatch(r"\d{11}", value):
            raise ValidationError("门诊号格式不正确，应为11位数字（例如 20260416001）。")
        exists = Patient.objects.filter(outpatient_number=value)
        if self.instance.pk:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise ValidationError("门诊号已存在，请输入唯一门诊号。")
        return value


class TreatmentForm(forms.ModelForm):
    prescription_template_id = forms.ChoiceField(
        label="处方模板",
        required=False,
        choices=[],
    )
    prescription_usage_method = forms.CharField(
        label="用药方式",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    prescription_items_json = forms.CharField(required=False, widget=forms.HiddenInput())
    scale_records_json = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get("start_date"):
            self.initial["start_date"] = timezone.localdate()
            self.fields["start_date"].initial = self.initial["start_date"]
        for field_name in [
            "chief_complaint",
            "tongue_diagnosis",
            "pulse_diagnosis",
            "treatment_principle",
            "auxiliary_exam_results",
        ]:
            self.fields[field_name].widget.attrs.setdefault("rows", 2)
        for field_name in [
            "past_history",
            "personal_history",
            "marital_history",
            "allergy_history",
            "family_history",
            "notes",
        ]:
            self.fields[field_name].widget.attrs.setdefault("rows", 2)
        self.fields["present_illness"].widget.attrs.setdefault("rows", 2)
        self.fields["prescription_usage_method"].widget.attrs.setdefault("rows", 2)
        self.fields["group_name"].widget.attrs.setdefault("placeholder", "例如：江苏省中医院")
        self.fields["chief_complaint"].widget.attrs["data-term-category"] = ClinicalTerm.CATEGORY_SYMPTOM
        self.fields["chief_complaint"].widget.attrs["data-term-autocomplete"] = "true"
        self.fields["tongue_diagnosis"].widget.attrs["data-term-category"] = ClinicalTerm.CATEGORY_SYMPTOM
        self.fields["tongue_diagnosis"].widget.attrs["data-term-autocomplete"] = "true"
        self.fields["pulse_diagnosis"].widget.attrs["data-term-category"] = ClinicalTerm.CATEGORY_SYMPTOM
        self.fields["pulse_diagnosis"].widget.attrs["data-term-autocomplete"] = "true"
        template_choices = [("", "")]
        template_choices.extend(
            (str(item.pk), item.name)
            for item in PrescriptionTemplate.objects.filter(is_active=True).order_by("name").only("id", "name")
        )
        self.fields["prescription_template_id"].choices = template_choices
        if self.instance.pk:
            items = [
                {
                    "herb_name": item.herb_name,
                    "dosage": item.dosage,
                    "unit": item.unit,
                    "usage": item.usage,
                }
                for item in self.instance.prescription_items.all()
            ]
            self.initial.setdefault(
                "prescription_items_json",
                json.dumps(items, ensure_ascii=False),
            )
            self.initial.setdefault(
                "prescription_usage_method",
                self.instance.prescription_usage_method,
            )
            existing_scale_records = []
            for record in self.instance.scale_records.select_related("template").all():
                existing_scale_records.append(
                    {
                        "template_id": record.template_id,
                        "template_name": record.template.name,
                        "notes": record.notes,
                        "answers": record.answers_json,
                    }
                )
            self.initial.setdefault(
                "scale_records_json",
                json.dumps(existing_scale_records, ensure_ascii=False),
            )
        else:
            self.initial.setdefault("scale_records_json", "[]")

    def clean_scale_records_json(self):
        return _normalize_scale_records(self.cleaned_data.get("scale_records_json"))

    def clean_prescription_items_json(self):
        raw_value = (self.cleaned_data.get("prescription_items_json") or "").strip()
        if not raw_value:
            return []
        try:
            items = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValidationError("处方明细数据格式错误，请重新录入。") from exc
        if not isinstance(items, list):
            raise ValidationError("处方明细数据格式错误，请重新录入。")

        cleaned_items = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            herb_name = (item.get("herb_name") or "").strip()
            dosage = (item.get("dosage") or "").strip()
            unit = (item.get("unit") or "").strip() or "g"
            usage = (item.get("usage") or "").strip()
            if not herb_name and not dosage and not usage:
                continue
            if not herb_name:
                raise ValidationError(f"第 {index} 味中药未填写名称。")
            cleaned_items.append(
                {
                    "herb_name": herb_name,
                    "dosage": dosage,
                    "unit": unit,
                    "usage": usage,
                    "sort_order": len(cleaned_items),
                }
            )
        _ensure_unique_herb_names(
            cleaned_items,
            message_builder=lambda index, herb_name: f"第 {index} 味“{herb_name}”与前面饮片重复，请调整后再保存。",
        )
        return cleaned_items

    class Meta:
        model = Treatment
        fields = [
            "group_name",
            "treatment_name",
            "start_date",
            "admission_date",
            "discharge_date",
            "total_weeks",
            "followup_interval_days",
            "chief_complaint",
            "present_illness",
            "past_history",
            "personal_history",
            "marital_history",
            "allergy_history",
            "family_history",
            "tongue_diagnosis",
            "pulse_diagnosis",
            "tcm_disease",
            "western_disease",
            "treatment_principle",
            "pathogenesis",
            "symptom_syndrome",
            "prescription_usage_method",
            "auxiliary_exam_results",
            "notes",
        ]
        widgets = {
            "start_date": DateInput(),
            "admission_date": DateInput(),
            "discharge_date": DateInput(),
        }

    def save_prescription_items(self, treatment):
        _replace_prescription_items(
            treatment,
            self.cleaned_data.get("prescription_items_json", []),
        )

    def save_scale_records(self, treatment, actor=None):
        _replace_scale_records(
            treatment=treatment,
            items=self.cleaned_data.get("scale_records_json", []),
            actor=actor,
        )


class FollowUpForm(forms.ModelForm):
    scale_records_json = forms.CharField(required=False, widget=forms.HiddenInput())

    next_followup_in_days = forms.IntegerField(
        label="距下次随访天数",
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "step": 1,
                "placeholder": "例如 30",
            }
        ),
        help_text="填写天数后，会按本次随访日期自动推算下次随访日期。",
    )

    def __init__(self, *args, treatment=None, **kwargs):
        self.treatment = treatment or getattr(kwargs.get("instance"), "treatment", None)
        super().__init__(*args, **kwargs)
        self.fields["symptoms"].widget.attrs.setdefault("rows", 4)
        self.fields["adverse_events"].widget.attrs.setdefault("rows", 1)
        self.fields["auxiliary_exam_results"].widget.attrs.setdefault("rows", 4)
        self.fields["notes"].widget.attrs.setdefault("rows", 1)
        self.fields["symptoms"].widget.attrs["data-term-category"] = ClinicalTerm.CATEGORY_SYMPTOM
        self.fields["symptoms"].widget.attrs["data-term-autocomplete"] = "true"

        if not self.treatment:
            return

        interval_days = self.treatment.followup_interval_days

        if not self.instance.pk and not self.initial.get("followup_date"):
            self.initial["followup_date"] = timezone.localdate()
            self.fields["followup_date"].initial = self.initial["followup_date"]

        followup_date = self.initial.get("followup_date") or self.instance.followup_date
        planned_next = (
            self.initial.get("planned_next_followup_date")
            or self.instance.planned_next_followup_date
        )

        if followup_date and not planned_next:
            planned_next = followup_date + timedelta(days=interval_days)
            self.initial["planned_next_followup_date"] = planned_next
            self.fields["planned_next_followup_date"].initial = planned_next

        if self.instance.pk and self.instance.followup_date and self.instance.planned_next_followup_date:
            delta_days = (self.instance.planned_next_followup_date - self.instance.followup_date).days
            self.initial.setdefault("next_followup_in_days", max(delta_days, 0))
        else:
            self.initial.setdefault("next_followup_in_days", interval_days)

        self.fields["next_followup_in_days"].initial = self.initial["next_followup_in_days"]
        existing_scale_records = []
        if self.instance.pk:
            for record in self.instance.scale_records.select_related("template").all():
                existing_scale_records.append(
                    {
                        "template_id": record.template_id,
                        "template_name": record.template.name,
                        "notes": record.notes,
                        "answers": record.answers_json,
                    }
                )
        self.initial.setdefault(
            "scale_records_json",
            json.dumps(existing_scale_records, ensure_ascii=False),
        )

    def clean(self):
        cleaned_data = super().clean()
        visit_number = cleaned_data.get("visit_number")
        treatment = self.treatment

        if visit_number and treatment:
            queryset = treatment.followups.filter(visit_number=visit_number)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                self.add_error("visit_number", "该次随访编号已存在，请勿重复录入。")

        followup_date = cleaned_data.get("followup_date")
        next_followup_in_days = cleaned_data.get("next_followup_in_days")
        planned_next_followup_date = cleaned_data.get("planned_next_followup_date")

        if treatment and followup_date:
            if next_followup_in_days is not None:
                planned_next_followup_date = followup_date + timedelta(days=next_followup_in_days)
                cleaned_data["planned_next_followup_date"] = planned_next_followup_date
            elif not planned_next_followup_date:
                planned_next_followup_date = followup_date + timedelta(
                    days=treatment.followup_interval_days
                )
                cleaned_data["planned_next_followup_date"] = planned_next_followup_date

        if followup_date and planned_next_followup_date:
            if planned_next_followup_date < followup_date:
                self.add_error("planned_next_followup_date", "下次随访日期不能早于本次随访日期。")
            cleaned_data["next_followup_in_days"] = (
                planned_next_followup_date - followup_date
            ).days

        return cleaned_data

    def clean_scale_records_json(self):
        return _normalize_scale_records(self.cleaned_data.get("scale_records_json"))

    class Meta:
        model = FollowUp
        fields = [
            "visit_number",
            "followup_date",
            "planned_next_followup_date",
            "symptoms",
            "medication_adherence",
            "adverse_events",
            "auxiliary_exam_results",
            "notes",
        ]
        widgets = {
            "followup_date": DateInput(),
            "planned_next_followup_date": DateInput(),
        }

    def save_scale_records(self, followup, actor=None):
        _replace_scale_records(
            followup=followup,
            items=self.cleaned_data.get("scale_records_json", []),
            actor=actor,
        )


class PatientFilterForm(forms.Form):
    VIEW_CHOICES = [
        ("card", "卡片视图"),
        ("table", "列表视图"),
    ]
    STATUS_CHOICES = [
        ("", "全部状态"),
        ("today", "今日回访"),
        ("active", "随访中"),
        ("done", "已完成"),
        ("overdue", "已逾期"),
    ]

    q = forms.CharField(label="关键词", required=False)
    tcm_disease = forms.CharField(label="中医疾病", required=False)
    status = forms.ChoiceField(label="状态", required=False, choices=STATUS_CHOICES)
    start_date_from = forms.DateField(label="开始时间从", required=False, widget=DateInput())
    start_date_to = forms.DateField(label="开始时间到", required=False, widget=DateInput())
    view = forms.ChoiceField(label="视图", required=False, choices=VIEW_CHOICES)


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="用户名")
    password = forms.CharField(label="密码", widget=forms.PasswordInput)


class AccountCreateForm(UserCreationForm):
    ROLE_CHOICES = [
        (UserProfile.ROLE_ADMIN, "管理员"),
        (UserProfile.ROLE_NORMAL, "普通"),
    ]

    role = forms.ChoiceField(label="账号类型", choices=ROLE_CHOICES)
    first_name = forms.CharField(label="姓名", required=False)
    modify_window_days = forms.IntegerField(
        label="可修改/删除历史数据天数",
        min_value=1,
        help_text="管理员默认 365 天，普通账号默认 3 天。",
    )
    project_permissions = forms.ModelMultipleChoiceField(
        label="项目权限",
        required=False,
        queryset=ResearchProject.objects.none(),
        help_text="管理员和普通账号都按此授权项目。未选择则看不到任何项目。",
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "role",
            "modify_window_days",
            "project_permissions",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        default_role = self.initial.get("role") or UserProfile.ROLE_ADMIN
        self.fields["modify_window_days"].initial = UserProfile.default_modify_window_days(
            default_role
        )
        self.fields["project_permissions"].queryset = ResearchProject.objects.order_by("-created_at", "name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("first_name", "")
        user.is_active = True
        if commit:
            user.save()
            profile, _ = UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": self.cleaned_data["role"],
                    "modify_window_days": self.cleaned_data["modify_window_days"],
                },
            )
            if profile.role in {UserProfile.ROLE_ADMIN, UserProfile.ROLE_NORMAL}:
                profile.allowed_projects.set(self.cleaned_data.get("project_permissions"))
            else:
                profile.allowed_projects.clear()
        return user


class AccountUpdateForm(forms.ModelForm):
    ROLE_CHOICES = [
        (UserProfile.ROLE_ADMIN, "管理员"),
        (UserProfile.ROLE_NORMAL, "普通"),
    ]

    role = forms.ChoiceField(label="账号类型", choices=ROLE_CHOICES)
    modify_window_days = forms.IntegerField(
        label="可修改/删除历史数据天数",
        min_value=1,
        help_text="管理员默认 365 天，普通账号默认 3 天。",
    )
    project_permissions = forms.ModelMultipleChoiceField(
        label="项目权限",
        required=False,
        queryset=ResearchProject.objects.none(),
        help_text="管理员和普通账号都按此授权项目。未选择则看不到任何项目。",
    )
    new_password1 = forms.CharField(
        label="新密码",
        required=False,
        widget=forms.PasswordInput,
        help_text="不修改密码可留空。",
    )
    new_password2 = forms.CharField(
        label="确认新密码",
        required=False,
        widget=forms.PasswordInput,
        help_text="如填写新密码，需要再次输入确认。",
    )

    class Meta:
        model = User
        fields = ("username", "first_name")
        labels = {
            "username": "用户名",
            "first_name": "姓名",
        }

    def __init__(self, *args, **kwargs):
        self.profile = kwargs.pop("profile")
        super().__init__(*args, **kwargs)
        self.fields["role"].initial = self.profile.role
        self.fields["modify_window_days"].initial = self.profile.effective_modify_window_days
        self.fields["project_permissions"].queryset = ResearchProject.objects.order_by("-created_at", "name")
        self.fields["project_permissions"].initial = self.profile.allowed_projects.all()

    def clean(self):
        cleaned_data = super().clean()
        password_1 = cleaned_data.get("new_password1")
        password_2 = cleaned_data.get("new_password2")
        if password_1 or password_2:
            if password_1 != password_2:
                raise ValidationError("两次输入的新密码不一致。")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = True
        new_password = self.cleaned_data.get("new_password1")
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
            self.profile.role = self.cleaned_data["role"]
            self.profile.modify_window_days = self.cleaned_data["modify_window_days"]
            self.profile.save()
            if self.profile.role in {UserProfile.ROLE_ADMIN, UserProfile.ROLE_NORMAL}:
                self.profile.allowed_projects.set(self.cleaned_data.get("project_permissions"))
            else:
                self.profile.allowed_projects.clear()
        return user


class ClinicalTermForm(forms.ModelForm):
    class Meta:
        model = ClinicalTerm
        fields = ["category", "name", "alias"]
        labels = {
            "category": "术语分类",
            "name": "术语名称",
            "alias": "别名/关键词",
        }


class ClinicalTermBatchImportForm(forms.Form):
    category = forms.ChoiceField(label="术语分类", choices=ClinicalTerm.CATEGORY_CHOICES)
    items_text = forms.CharField(
        label="批量导入内容",
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="每行一个术语。格式：术语名称 或 术语名称|别名1,别名2。多个别名用中文或英文逗号分隔。",
    )

    def clean_items_text(self):
        raw_text = (self.cleaned_data.get("items_text") or "").strip()
        if not raw_text:
            raise ValidationError("请至少填写一条术语。")
        return raw_text

    def parse_items(self):
        raw_text = self.cleaned_data["items_text"]
        rows = []
        failures = []
        for index, line in enumerate(raw_text.splitlines(), start=1):
            raw_line = line.strip()
            if not raw_line:
                continue
            if raw_line.count("|") > 1:
                failures.append({"line_no": index, "content": raw_line, "reason": "分隔符“|”数量不正确"})
                continue
            parts = [item.strip() for item in raw_line.split("|", 1)]
            name = parts[0]
            alias = parts[1] if len(parts) == 2 else ""
            if not name:
                failures.append({"line_no": index, "content": raw_line, "reason": "术语名称不能为空"})
                continue
            rows.append({"name": name, "alias": alias})
        return rows, failures


class ScaleTemplateManageForm(forms.ModelForm):
    items_text = forms.CharField(
        label="量表结构定义",
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="支持分组和父子题。group|分组编码|大标题|介绍；score|题目编码|分组编码|条目名称|提示语|最小分|最大分|父题编码；text/textarea|题目编码|分组编码|条目名称|提示语|父题编码；number|题目编码|分组编码|条目名称|提示语|最小值|最大值|父题编码；select|题目编码|分组编码|条目名称|提示语|选项1,选项2|父题编码。",
    )

    class Meta:
        model = ScaleTemplate
        fields = ["name", "description"]
        labels = {
            "name": "量表名称",
            "description": "量表说明",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            lines = []
            for item in self.instance.items.all():
                if item.field_type == ScaleTemplateItem.FIELD_GROUP:
                    lines.append(
                        f"group|{item.group_key or item.item_key}|{item.label}|{item.help_text}"
                    )
                elif item.field_type in {ScaleTemplateItem.FIELD_SCORE, ScaleTemplateItem.FIELD_NUMBER}:
                    lines.append(
                        f"{item.field_type}|{item.item_key}|{item.group_key}|{item.label}|{item.help_text}|{item.score_min}|{item.score_max}|{item.parent_key}"
                    )
                elif item.field_type == ScaleTemplateItem.FIELD_SELECT:
                    lines.append(
                        f"{item.field_type}|{item.item_key}|{item.group_key}|{item.label}|{item.help_text}|{item.options_text}|{item.parent_key}"
                    )
                else:
                    lines.append(f"{item.field_type}|{item.item_key}|{item.group_key}|{item.label}|{item.help_text}|{item.parent_key}")
            self.initial.setdefault("items_text", "\n".join(lines))

    def clean_items_text(self):
        raw_text = (self.cleaned_data.get("items_text") or "").strip()
        if not raw_text:
            raise ValidationError("请至少填写一个量表条目。")
        rows = []
        for index, line in enumerate(raw_text.splitlines(), start=1):
            raw_line = line.strip()
            if not raw_line:
                continue
            parts = [item.strip() for item in raw_line.split("|")]
            if len(parts) < 2:
                raise ValidationError(f"第 {index} 行格式不正确。")
            field_type = (parts[0] or ScaleTemplateItem.FIELD_SCORE).lower()
            if field_type not in {choice[0] for choice in ScaleTemplateItem.FIELD_TYPE_CHOICES}:
                raise ValidationError(f"第 {index} 行题型无效。")
            if field_type == ScaleTemplateItem.FIELD_GROUP:
                if len(parts) != 4:
                    raise ValidationError(f"第 {index} 行分组格式应为：group|分组编码|大标题|介绍。")
                group_key = _normalize_scale_key(parts[1], f"group_{index}")
                label = parts[2]
                help_text = parts[3]
                if not label:
                    raise ValidationError(f"第 {index} 行分组标题不能为空。")
                rows.append(
                    {
                        "label": label,
                        "field_type": field_type,
                        "item_key": group_key,
                        "group_key": group_key,
                        "parent_key": "",
                        "help_text": help_text,
                        "score_min": 0,
                        "score_max": 0,
                        "options_text": "",
                        "sort_order": len(rows),
                    }
                )
                continue

            if len(parts) < 5:
                raise ValidationError(f"第 {index} 行格式不完整。")
            item_key = _normalize_scale_key(parts[1], f"item_{index}")
            group_key = _normalize_scale_key(parts[2], "") if parts[2] else ""
            label = parts[3]
            help_text = parts[4]
            parent_key = ""
            if not label:
                raise ValidationError(f"第 {index} 行条目名称不能为空。")
            score_min = 0
            score_max = 6
            options_text = ""
            if field_type in {ScaleTemplateItem.FIELD_SCORE, ScaleTemplateItem.FIELD_NUMBER}:
                if len(parts) not in {7, 8}:
                    raise ValidationError(f"第 {index} 行需要填写完整的数值范围。")
                try:
                    score_min = int(parts[5])
                    score_max = int(parts[6])
                except ValueError as exc:
                    raise ValidationError(f"第 {index} 行数值范围必须是整数。") from exc
                if score_min > score_max:
                    raise ValidationError(f"第 {index} 行最小值不能大于最大值。")
                if len(parts) == 8:
                    parent_key = _normalize_scale_key(parts[7], "") if parts[7] else ""
            elif field_type == ScaleTemplateItem.FIELD_SELECT:
                if len(parts) not in {6, 7}:
                    raise ValidationError(f"第 {index} 行单选题需要提供选项列表。")
                options = _parse_scale_options(parts[5])
                if not options:
                    raise ValidationError(f"第 {index} 行至少要有一个可选项。")
                options_text = ",".join(options)
                if len(parts) == 7:
                    parent_key = _normalize_scale_key(parts[6], "") if parts[6] else ""
            elif len(parts) not in {5, 6}:
                raise ValidationError(f"第 {index} 行格式不正确。")
            elif len(parts) == 6:
                parent_key = _normalize_scale_key(parts[5], "") if parts[5] else ""
            rows.append(
                {
                    "label": label,
                    "field_type": field_type,
                    "item_key": item_key,
                    "group_key": group_key,
                    "parent_key": parent_key,
                    "help_text": help_text,
                    "score_min": score_min,
                    "score_max": score_max,
                    "options_text": options_text,
                    "sort_order": len(rows),
                }
            )
        if not rows:
            raise ValidationError("请至少填写一个量表条目。")
        return rows

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.is_active = True
        if commit:
            instance.save()
        return instance

    def save_items(self, template):
        template.items.all().delete()
        ScaleTemplateItem.objects.bulk_create(
            [
                ScaleTemplateItem(
                    template=template,
                    label=item["label"],
                    field_type=item["field_type"],
                    item_key=item["item_key"],
                    group_key=item["group_key"],
                    parent_key=item["parent_key"],
                    help_text=item["help_text"],
                    score_min=item["score_min"],
                    score_max=item["score_max"],
                    options_text=item["options_text"],
                    sort_order=item["sort_order"],
                )
                for item in self.cleaned_data["items_text"]
            ]
        )


class PrescriptionTemplateManageForm(forms.ModelForm):
    items_text = forms.CharField(
        label="处方条目定义",
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="每行一个药味，格式：饮片名称|剂量|单位|脚注。例如：黄芪|15|g|先煎",
    )

    class Meta:
        model = PrescriptionTemplate
        fields = ["name", "usage_method", "notes"]
        labels = {
            "name": "处方名称",
            "usage_method": "用药方式",
            "notes": "备注",
        }
        widgets = {
            "usage_method": forms.Textarea(attrs={"rows": 1}),
            "notes": forms.Textarea(attrs={"rows": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            lines = []
            for item in self.instance.items.all():
                lines.append(
                    f"{item.herb_name}|{item.dosage}|{item.unit}|{item.usage}"
                )
            self.initial.setdefault("items_text", "\n".join(lines))

    def clean_items_text(self):
        raw_text = (self.cleaned_data.get("items_text") or "").strip()
        if not raw_text:
            raise ValidationError("请至少填写一个处方条目。")
        rows = []
        for index, line in enumerate(raw_text.splitlines(), start=1):
            raw_line = line.strip()
            if not raw_line:
                continue
            parts = [item.strip() for item in raw_line.split("|")]
            if len(parts) == 1:
                herb_name, dosage, unit, usage = parts[0], "", "g", ""
            elif len(parts) == 4:
                herb_name, dosage, unit, usage = parts
            else:
                raise ValidationError(f"第 {index} 行格式不正确。")
            if not herb_name:
                raise ValidationError(f"第 {index} 行饮片名称不能为空。")
            rows.append(
                {
                    "herb_name": herb_name,
                    "dosage": dosage,
                    "unit": unit or "g",
                    "usage": usage,
                    "sort_order": len(rows),
                }
            )
        if not rows:
            raise ValidationError("请至少填写一个处方条目。")
        _ensure_unique_herb_names(
            rows,
            message_builder=lambda index, herb_name: f"第 {index} 行饮片“{herb_name}”重复，请删除或合并。",
        )
        return rows

    def save_items(self, template):
        template.items.all().delete()
        PrescriptionTemplateItem.objects.bulk_create(
            [
                PrescriptionTemplateItem(
                    template=template,
                    herb_name=item["herb_name"],
                    dosage=item["dosage"],
                    unit=item["unit"],
                    usage=item["usage"],
                    sort_order=item["sort_order"],
                )
                for item in self.cleaned_data["items_text"]
            ]
        )


class ResearchProjectForm(forms.ModelForm):
    class Meta:
        model = ResearchProject
        fields = ["name", "principal_investigator", "status", "target_enrollment", "notes"]
        labels = {
            "name": "项目名称",
            "principal_investigator": "负责人",
            "status": "项目状态",
            "target_enrollment": "目标例数",
            "notes": "项目备注",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "例如：慢痞消项目"}),
            "principal_investigator": forms.TextInput(attrs={"placeholder": "负责人姓名"}),
            "target_enrollment": forms.NumberInput(attrs={"min": 0}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class ProjectEnrollmentBatchForm(forms.Form):
    q = forms.CharField(required=False, label="患者检索", max_length=50)
    group_name = forms.CharField(required=False, label="项目分组", max_length=60)
    enrollment_date = forms.DateField(required=False, label="入组日期", widget=DateInput())
    notes = forms.CharField(required=False, label="入组备注", widget=forms.Textarea(attrs={"rows": 2}))
    selected_patient_ids = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group_name"].widget.attrs.setdefault("placeholder", "例如：治疗组A")
        self.fields["enrollment_date"].widget.attrs.setdefault("placeholder", "YYYY-MM-DD")

    def clean_selected_patient_ids(self):
        raw_value = (self.cleaned_data.get("selected_patient_ids") or "").strip()
        if not raw_value:
            return []
        values = []
        seen = set()
        for part in raw_value.split(","):
            item = part.strip()
            if not item.isdigit():
                continue
            value = int(item)
            if value in seen:
                continue
            seen.add(value)
            values.append(value)
        return values


class ProjectEnrollmentMarkerForm(forms.ModelForm):
    class Meta:
        model = ProjectEnrollment
        fields = ["marker_status", "marker_date", "marker_note"]
        labels = {
            "marker_status": "标记",
            "marker_date": "标记日期",
            "marker_note": "标记说明",
        }
        widgets = {
            "marker_date": DateInput(),
            "marker_note": forms.TextInput(attrs={"placeholder": "请填写标记说明"}),
        }

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("marker_status")
        note = (cleaned.get("marker_note") or "").strip()
        if status and status != ProjectEnrollment.MARKER_IN and not note:
            self.add_error("marker_note", "非“在组”时，标记说明不能为空。")
        return cleaned
