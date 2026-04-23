import csv
import io
import json
import logging
import mimetypes
import os
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from types import SimpleNamespace
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Max, OuterRef, Prefetch, Q, Subquery
from django.db.models.deletion import ProtectedError
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .ai import AIServiceError, chat_with_patient
from .forms import (
    _build_prescription_templates_payload,
    _build_scale_templates_payload,
    AccountCreateForm,
    AccountUpdateForm,
    ClinicalTermBatchImportForm,
    ClinicalTermForm,
    FollowUpForm,
    LoginForm,
    PatientFilterForm,
    PatientForm,
    ProjectEnrollmentBatchForm,
    ProjectEnrollmentMarkerForm,
    PrescriptionTemplateManageForm,
    ResearchProjectForm,
    ScaleTemplateManageForm,
    TreatmentForm,
)
from .models import (
    AuxiliaryExamAttachment,
    ClinicalTerm,
    FollowUp,
    Patient,
    ProjectEnrollment,
    PrescriptionTemplate,
    ResearchProject,
    ScaleRecord,
    ScaleTemplate,
    Treatment,
    UserProfile,
)
from .permissions import (
    can_access_project,
    can_export_data,
    can_export_project_data,
    can_manage_accounts,
    can_manage_project_definition,
    can_manage_project_module,
    can_manage_reference_data,
    can_modify_record,
    get_project_queryset_for_user,
    get_modify_window_days,
    get_user_profile,
    get_user_role,
    get_user_role_label,
)


STATUS_NOT_STARTED = "未开始"
STATUS_ACTIVE = "随访中"
STATUS_DONE = "已完成"
STATUS_OVERDUE = "已逾期"
STATUS_TODAY = "今日回访"
PROJECT_MARKER_LABELS = {
    ProjectEnrollment.MARKER_IN: "在组",
    ProjectEnrollment.MARKER_COMPLETED: "完成",
    ProjectEnrollment.MARKER_WITHDRAWN: "退出",
    ProjectEnrollment.MARKER_LOST: "脱落",
}
PROJECT_MARKER_WITHDRAWN_ALIASES = {
    ProjectEnrollment.MARKER_PROTOCOL,
    ProjectEnrollment.MARKER_ADVERSE,
    ProjectEnrollment.MARKER_DEATH,
    ProjectEnrollment.MARKER_TRANSFER,
    ProjectEnrollment.MARKER_PROJECT_END,
}


logger = logging.getLogger(__name__)
_ROW_CACHE_TTL_SECONDS = 180
_ROW_CACHE_MAX_ITEMS = 8
_PATIENT_ROW_CACHE = {}
_PATIENT_FILTER_CACHE = {}
_PROJECT_ENROLLMENT_BASE_CACHE = {}
_PATIENT_STATS_CACHE = {}
_PROJECT_ENROLLMENT_VIEW_CACHE = {}


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
    if len(bucket) >= _ROW_CACHE_MAX_ITEMS:
        expired_keys = [item_key for item_key, item in bucket.items() if item["expires_at"] <= now]
        for item_key in expired_keys:
            bucket.pop(item_key, None)
        if len(bucket) >= _ROW_CACHE_MAX_ITEMS:
            oldest_key = min(bucket, key=lambda item_key: bucket[item_key]["expires_at"])
            bucket.pop(oldest_key, None)
    bucket[key] = {"expires_at": now + _ROW_CACHE_TTL_SECONDS, "value": value}


def _clone_rows(rows):
    return [dict(item) for item in rows]


def _normalize_cache_dt(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _patient_row_cache_signature():
    patient_agg = Patient.objects.aggregate(
        count=Count("id"),
        max_created=Max("created_at"),
        max_updated=Max("updated_at"),
    )
    treatment_agg = Treatment.objects.aggregate(
        count=Count("id"),
        max_created=Max("created_at"),
        max_updated=Max("updated_at"),
    )
    followup_agg = FollowUp.objects.aggregate(
        count=Count("id"),
        max_created=Max("created_at"),
        max_updated=Max("updated_at"),
    )
    enrollment_agg = ProjectEnrollment.objects.aggregate(
        count=Count("id"),
        max_created=Max("created_at"),
        max_marker_updated=Max("marker_updated_at"),
    )
    project_agg = ResearchProject.objects.aggregate(
        count=Count("id"),
        max_created=Max("created_at"),
        max_updated=Max("updated_at"),
    )
    return (
        patient_agg.get("count", 0),
        _normalize_cache_dt(patient_agg.get("max_created")),
        _normalize_cache_dt(patient_agg.get("max_updated")),
        treatment_agg.get("count", 0),
        _normalize_cache_dt(treatment_agg.get("max_created")),
        _normalize_cache_dt(treatment_agg.get("max_updated")),
        followup_agg.get("count", 0),
        _normalize_cache_dt(followup_agg.get("max_created")),
        _normalize_cache_dt(followup_agg.get("max_updated")),
        enrollment_agg.get("count", 0),
        _normalize_cache_dt(enrollment_agg.get("max_created")),
        _normalize_cache_dt(enrollment_agg.get("max_marker_updated")),
        project_agg.get("count", 0),
        _normalize_cache_dt(project_agg.get("max_created")),
        _normalize_cache_dt(project_agg.get("max_updated")),
    )
_PINYIN_INITIAL_RANGE = [
    (-20319, -20284, "A"),
    (-20283, -19776, "B"),
    (-19775, -19219, "C"),
    (-19218, -18711, "D"),
    (-18710, -18527, "E"),
    (-18526, -18240, "F"),
    (-18239, -17923, "G"),
    (-17922, -17418, "H"),
    (-17417, -16475, "J"),
    (-16474, -16213, "K"),
    (-16212, -15641, "L"),
    (-15640, -15166, "M"),
    (-15165, -14923, "N"),
    (-14922, -14915, "O"),
    (-14914, -14631, "P"),
    (-14630, -14150, "Q"),
    (-14149, -14091, "R"),
    (-14090, -13319, "S"),
    (-13318, -12839, "T"),
    (-12838, -12557, "W"),
    (-12556, -11848, "X"),
    (-11847, -11056, "Y"),
    (-11055, -10247, "Z"),
]
_PINYIN_INITIAL_FALLBACK = {
    "芪": "Q",
    "藁": "G",
    "麸": "F",
    "薏": "Y",
    "瞿": "Q",
    "槲": "H",
    "莪": "E",
    "蜣": "Q",
    "蛴": "Q",
    "蝉": "C",
}


def _normalize_project_marker_status(raw_value):
    value = (raw_value or "").strip()
    if value in PROJECT_MARKER_LABELS:
        return value
    if value in PROJECT_MARKER_WITHDRAWN_ALIASES:
        return ProjectEnrollment.MARKER_WITHDRAWN
    return ProjectEnrollment.MARKER_IN


def _project_marker_label(raw_value):
    return PROJECT_MARKER_LABELS[_normalize_project_marker_status(raw_value)]


def _redirect_with_error(request, message, target, *args):
    messages.error(request, message)
    return redirect(target, *args)


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _char_to_pinyin_initial(char):
    if not char:
        return ""
    if char.isascii() and char.isalnum():
        return char.upper()
    if char in _PINYIN_INITIAL_FALLBACK:
        return _PINYIN_INITIAL_FALLBACK[char]
    try:
        encoded = char.encode("gb2312")
    except UnicodeEncodeError:
        return ""
    if len(encoded) != 2:
        return ""
    code = encoded[0] * 256 + encoded[1] - 65536
    for start, end, initial in _PINYIN_INITIAL_RANGE:
        if start <= code <= end:
            return initial
    return ""


def _to_pinyin_initials(text):
    return "".join(_char_to_pinyin_initial(char) for char in (text or "").strip())


def _is_initial_keyword(keyword):
    return bool(re.fullmatch(r"[a-zA-Z0-9]+", keyword or ""))


def _compute_term_match_priority(term, keyword, use_initial_match=False):
    keyword_lower = (keyword or "").lower()
    name = (term.name or "").strip()
    alias = (term.alias or "").strip()
    name_lower = name.lower()
    alias_lower = alias.lower()
    if name_lower.startswith(keyword_lower):
        return 0
    if alias_lower.startswith(keyword_lower):
        return 1
    if keyword_lower in name_lower:
        return 2
    if keyword_lower in alias_lower:
        return 3
    if use_initial_match:
        name_initials = _to_pinyin_initials(name).lower()
        alias_initials = _to_pinyin_initials(alias).lower()
        if name_initials.startswith(keyword_lower):
            return 4
        if alias_initials.startswith(keyword_lower):
            return 5
        if keyword_lower in name_initials:
            return 6
        if keyword_lower in alias_initials:
            return 7
    return 8


def _term_suggestions(category, keyword, limit=12):
    keyword = (keyword or "").strip()
    queryset = ClinicalTerm.objects.filter(category=category, is_active=True)
    if not keyword:
        return list(queryset.order_by("sort_order", "name")[:limit])

    db_matches = list(
        queryset.filter(Q(name__icontains=keyword) | Q(alias__icontains=keyword)).order_by("sort_order", "name")[
            : limit * 4
        ]
    )
    use_initial_match = _is_initial_keyword(keyword)
    candidate_rows = list(queryset.order_by("sort_order", "name")) if use_initial_match else db_matches
    ranked = []
    seen_ids = set()
    for item in candidate_rows:
        priority = _compute_term_match_priority(item, keyword, use_initial_match=use_initial_match)
        if priority >= 8:
            continue
        ranked.append((priority, item.sort_order, item.name, item))
        seen_ids.add(item.pk)

    if not ranked and db_matches:
        for item in db_matches:
            if item.pk in seen_ids:
                continue
            ranked.append((8, item.sort_order, item.name, item))

    ranked.sort(key=lambda row: (row[0], row[1], row[2]))
    return [item for _, _, _, item in ranked[:limit]]


def _merge_alias_text(existing_alias, incoming_alias):
    values = []
    seen = set()
    for raw_group in [existing_alias or "", incoming_alias or ""]:
        normalized = raw_group.replace("，", ",")
        for part in normalized.split(","):
            alias = part.strip()
            if not alias:
                continue
            key = alias.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append(alias)
    return ",".join(values)


def _split_term_tags(raw_text):
    seen = set()
    values = []
    for part in re.split(r"[，,、;；\n]+", raw_text or ""):
        item = part.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        values.append(item)
    return values


def _build_known_tag_items(raw_text, known_name_set):
    return [
        {
            "name": item,
            "known": item.lower() in known_name_set,
        }
        for item in _split_term_tags(raw_text)
    ]


def _scale_record_progress(record):
    prefetched_items = getattr(record.template, "_prefetched_objects_cache", {}).get("items")
    if prefetched_items is not None:
        total_count = sum(1 for item in prefetched_items if item.field_type != "group")
    else:
        total_count = record.template.items.exclude(field_type="group").count()
    filled_count = 0
    for answer in (record.answers_json or []):
        if not isinstance(answer, dict):
            continue
        value = answer.get("value", answer.get("score"))
        if str(value or "").strip():
            filled_count += 1
    if filled_count > total_count:
        filled_count = total_count
    return {"record": record, "filled_count": filled_count, "total_count": total_count}


def _serialize_scale_record_list(records):
    return [_scale_record_progress(record) for record in records]


def _normalize_scale_item_key(value, fallback):
    text = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", (value or "").strip()).strip("_")
    return text or fallback


def _build_scale_record_sections(record):
    items = list(record.template.items.all())
    answers = record.answers_json or []
    answer_by_key = {}
    answer_by_label = {}
    sequence_answers = []
    for answer in answers:
        row = answer if isinstance(answer, dict) else {}
        key = (row.get("key") or "").strip()
        label = (row.get("label") or "").strip()
        if key:
            answer_by_key[key] = row
        if label and label not in answer_by_label:
            answer_by_label[label] = row
        sequence_answers.append(row)

    sections = []
    section_map = {}
    default_section = {"key": "__default__", "title": "未分组条目", "description": "", "items": []}
    question_index = 0
    for index, item in enumerate(items, start=1):
        item_key = item.item_key or _normalize_scale_item_key(item.label, f"item_{index}")
        if item.field_type == "group":
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

        answer = answer_by_key.get(item_key)
        if answer is None:
            answer = answer_by_label.get(item.label)
        if answer is None and question_index < len(sequence_answers):
            answer = sequence_answers[question_index]
        question_index += 1
        answer = answer if isinstance(answer, dict) else {}
        value = answer.get("value", answer.get("score"))

        row = {
            "key": item_key,
            "group_key": item.group_key,
            "parent_key": item.parent_key,
            "label": item.label,
            "field_type": item.field_type,
            "help_text": item.help_text,
            "score_min": item.score_min,
            "score_max": item.score_max,
            "value": value if value not in (None,) else "",
            "note": (answer.get("note") or "").strip(),
        }
        if item.group_key and item.group_key in section_map:
            section_map[item.group_key]["items"].append(row)
        else:
            default_section["items"].append(row)

    if default_section["items"]:
        sections.append(default_section)
    return sections


def _ensure_export_permission(request):
    if can_export_data(request.user):
        return None
    return _redirect_with_error(request, "普通账号不能导出数据。", "patient_list")


def _ensure_reference_permission(request):
    if can_manage_reference_data(request.user):
        return None
    return _redirect_with_error(request, "只有管理员和 Root 可以管理术语与量表。", "patient_list")


def _ensure_project_module_permission(request):
    if can_manage_project_module(request.user):
        return None
    return _redirect_with_error(request, "当前账号无权访问项目管理。", "patient_list")


def _ensure_project_definition_permission(request):
    if can_manage_project_definition(request.user):
        return None
    return _redirect_with_error(request, "仅 Root 可新建、编辑或删除项目。", "project_list")


def _ensure_modify_permission(request, obj, target, *args):
    if can_modify_record(request.user, obj):
        return None
    modify_window_days = get_modify_window_days(request.user)
    limit_text = f"近 {modify_window_days} 天" if modify_window_days else "当前权限范围"
    return _redirect_with_error(
        request,
        f"当前账号只能修改或删除{limit_text}内创建的数据。",
        target,
        *args,
    )


def _scale_template_locked(template_id):
    return ScaleRecord.objects.filter(template_id=template_id).exists()


def _account_rows(current_user):
    project_names = dict(ResearchProject.objects.values_list("id", "name"))
    rows = []
    for user in (
        User.objects.select_related("profile")
        .prefetch_related("profile__allowed_projects")
        .order_by("date_joined", "username")
    ):
        profile = get_user_profile(user)
        role = get_user_role(user)
        allowed_project_ids = [item.id for item in profile.allowed_projects.all()] if profile else []
        if role == UserProfile.ROLE_ROOT:
            project_scope_text = "全部项目"
        else:
            allowed_names = [project_names.get(project_id, "") for project_id in allowed_project_ids]
            allowed_names = [item for item in allowed_names if item]
            if allowed_names:
                preview = "、".join(allowed_names[:3])
                suffix = f" 等 {len(allowed_names)} 个项目" if len(allowed_names) > 3 else ""
                project_scope_text = f"{preview}{suffix}"
            else:
                project_scope_text = "未分配项目权限"
        rows.append(
            {
                "user": user,
                "role": role,
                "role_label": get_user_role_label(user) or "普通",
                "modify_window_days": (
                    "不限制"
                    if role == UserProfile.ROLE_ROOT
                    else f"{(profile.effective_modify_window_days if profile else 3)} 天"
                ),
                "project_scope_text": project_scope_text,
                "can_manage": role != UserProfile.ROLE_ROOT,
                "can_delete": role != UserProfile.ROLE_ROOT and user.pk != current_user.pk,
            }
        )
    return rows


def login_view(request):
    if request.user.is_authenticated:
        return redirect("patient_list")

    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("patient_list")

    return render(
        request,
        "followup/login.html",
        {"form": form, "next_url": request.GET.get("next", "")},
    )


@login_required
def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("login")


@login_required
def term_suggest(request):
    category = (request.GET.get("category") or "").strip()
    keyword = (request.GET.get("q") or "").strip()
    allowed_categories = {item[0] for item in ClinicalTerm.CATEGORY_CHOICES}
    if category not in allowed_categories:
        return JsonResponse({"results": []})
    rows = _term_suggestions(category, keyword)
    return JsonResponse(
        {
            "results": [
                {
                    "name": item.name,
                    "alias": item.alias,
                    "category": item.category,
                }
                for item in rows
            ]
        }
    )


@login_required
def term_exists(request):
    category = (request.GET.get("category") or "").strip()
    name = (request.GET.get("name") or "").strip()
    allowed_categories = {item[0] for item in ClinicalTerm.CATEGORY_CHOICES}
    if category not in allowed_categories or not name:
        return JsonResponse({"exists": False})
    exists = ClinicalTerm.objects.filter(category=category, is_active=True, name__iexact=name).exists()
    return JsonResponse({"exists": exists})


@login_required
def prescription_template_payload(request):
    payload = _build_prescription_templates_payload()
    return JsonResponse({"results": payload.get("templates", [])})


@login_required
def scale_template_payload(request):
    payload = _build_scale_templates_payload()
    return JsonResponse({"results": payload})


@login_required
def account_list(request):
    if not can_manage_accounts(request.user):
        return _redirect_with_error(request, "只有 Root 可以管理账号。", "patient_list")
    return render(
        request,
        "followup/account_list.html",
        {
            "page_title": "账号管理",
            "account_rows": _account_rows(request.user),
            "admin_shortcuts": [
                {"label": "模版管理", "url": reverse("template_manage")},
            ],
        },
    )


@login_required
def template_manage(request):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied
    return render(
        request,
        "followup/template_manage.html",
        {
            "page_title": "模版管理",
            "modules": [
                {
                    "title": "术语管理",
                    "description": "维护固定分类术语与别名，用于诊疗/随访快速录入联想。",
                    "url": reverse("term_list"),
                },
                {
                    "title": "处方模板",
                    "description": "维护常用组方模板，按饮片逐味维护并支持录入时套用。",
                    "url": reverse("prescription_template_list"),
                },
                {
                    "title": "量表管理",
                    "description": "维护诊疗与随访共用量表模板，支持分组与多题型。",
                    "url": reverse("scale_template_list"),
                },
            ],
        },
    )


@login_required
def term_list(request):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied

    filter_category = (request.GET.get("filter_category") or "").strip()
    keyword = (request.GET.get("keyword") or "").strip()
    allowed_categories = {item[0] for item in ClinicalTerm.CATEGORY_CHOICES}
    if filter_category and filter_category not in allowed_categories:
        filter_category = ""

    form = ClinicalTermBatchImportForm(request.POST or None)
    if request.method == "POST":
        action = request.POST.get("action") or "import"
        if action == "delete":
            selected_ids = [item for item in request.POST.getlist("selected_term_ids") if item.isdigit()]
            deleted_count, _ = ClinicalTerm.objects.filter(pk__in=selected_ids).delete()
            messages.success(request, f"已删除 {deleted_count} 条术语。")
            redirect_url = reverse("term_list")
            query_data = {}
            if request.POST.get("current_filter_category"):
                query_data["filter_category"] = request.POST["current_filter_category"]
            if request.POST.get("current_keyword"):
                query_data["keyword"] = request.POST["current_keyword"]
            if query_data:
                redirect_url = f"{redirect_url}?{urlencode(query_data)}"
            return redirect(redirect_url)
        if form.is_valid():
            category = form.cleaned_data["category"]
            parsed_rows, failures = form.parse_items()
            created_count = 0
            updated_count = 0
            for item in parsed_rows:
                term, created = ClinicalTerm.objects.get_or_create(
                    category=category,
                    name=item["name"],
                    defaults={
                        "alias": item["alias"],
                        "is_active": True,
                    },
                )
                if created:
                    created_count += 1
                else:
                    merged_alias = _merge_alias_text(term.alias, item["alias"])
                    if merged_alias != (term.alias or ""):
                        term.alias = merged_alias
                        term.save(update_fields=["alias"])
                    updated_count += 1
            messages.success(
                request,
                f"术语导入完成：新增 {created_count} 条，补充/复用 {updated_count} 条，失败 {len(failures)} 条。"
            )
            if failures:
                failure_lines = "；".join(
                    f"第 {item['line_no']} 行：{item['content']}（{item['reason']}）"
                    for item in failures
                )
                messages.error(request, f"以下内容未导入：{failure_lines}")
            return redirect("term_list")

    category_groups = []
    for category_value, category_label in ClinicalTerm.CATEGORY_CHOICES:
        items_queryset = ClinicalTerm.objects.filter(category=category_value)
        if keyword:
            items_queryset = items_queryset.filter(
                Q(name__icontains=keyword) | Q(alias__icontains=keyword)
            )
        items = list(items_queryset.order_by("name", "id"))
        if filter_category and category_value != filter_category:
            items = []
        category_groups.append(
            {
                "value": category_value,
                "label": category_label,
                "count": len(items),
                "items": items,
            }
        )

    return render(
        request,
        "followup/term_list.html",
        {
            "page_title": "术语管理",
            "form": form,
            "category_groups": category_groups,
            "filter_category": filter_category,
            "keyword": keyword,
            "category_choices": ClinicalTerm.CATEGORY_CHOICES,
        },
    )


@login_required
def term_update(request, pk):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied
    term = get_object_or_404(ClinicalTerm, pk=pk)
    form = ClinicalTermForm(request.POST or None, instance=term)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "术语已更新。")
        return redirect("term_list")
    return render(
        request,
        "followup/reference_form.html",
        {
            "page_title": "编辑术语",
            "form": form,
            "cancel_url": reverse("term_list"),
            "submit_label": "保存术语",
        },
    )


@login_required
def term_delete(request, pk):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied
    term = get_object_or_404(ClinicalTerm, pk=pk)
    if request.method == "POST":
        term.delete()
        messages.success(request, "术语已删除。")
        return redirect("term_list")
    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除术语",
            "description": f"将删除术语“{term.name}”，此操作不可恢复。",
            "cancel_url": reverse("term_list"),
        },
    )


@login_required
def scale_template_list(request):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied

    form = ScaleTemplateManageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        template = form.save()
        form.save_items(template)
        messages.success(request, "量表模板已保存。")
        return redirect("scale_template_list")

    return render(
        request,
        "followup/scale_template_list.html",
        {
            "page_title": "量表管理",
            "form": form,
            "templates": ScaleTemplate.objects.prefetch_related("items").annotate(record_count=Count("records")),
        },
    )


@login_required
def scale_template_update(request, pk):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied
    if _scale_template_locked(pk):
        messages.error(request, "该量表已被录入使用，数据库已有数据，不能修改。")
        return redirect("scale_template_list")
    template = get_object_or_404(ScaleTemplate.objects.prefetch_related("items"), pk=pk)
    form = ScaleTemplateManageForm(request.POST or None, instance=template)
    if request.method == "POST" and form.is_valid():
        template = form.save()
        form.save_items(template)
        messages.success(request, "量表模板已更新。")
        return redirect("scale_template_list")
    return render(
        request,
        "followup/reference_form.html",
        {
            "page_title": "编辑量表",
            "form": form,
            "cancel_url": reverse("scale_template_list"),
            "submit_label": "保存量表",
        },
    )


@login_required
def scale_template_delete(request, pk):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied
    if _scale_template_locked(pk):
        messages.error(request, "该量表已被录入使用，数据库已有数据，不能删除。")
        return redirect("scale_template_list")
    template = get_object_or_404(ScaleTemplate, pk=pk)
    if request.method == "POST":
        try:
            template.delete()
            messages.success(request, "量表模板已删除。")
        except ProtectedError:
            messages.error(request, "该量表已被录入使用，数据库已有数据，不能删除。")
        return redirect("scale_template_list")
    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除量表",
            "description": f"将删除量表“{template.name}”及其条目，此操作不可恢复。",
            "cancel_url": reverse("scale_template_list"),
        },
    )


@login_required
def prescription_template_list(request):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied

    form = PrescriptionTemplateManageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        template = form.save()
        form.save_items(template)
        messages.success(request, "处方模板已保存。")
        return redirect("prescription_template_list")

    return render(
        request,
        "followup/prescription_template_list.html",
        {
            "page_title": "处方模板管理",
            "form": form,
            "templates": PrescriptionTemplate.objects.prefetch_related("items").all(),
        },
    )


@login_required
def prescription_template_update(request, pk):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied
    template = get_object_or_404(PrescriptionTemplate.objects.prefetch_related("items"), pk=pk)
    form = PrescriptionTemplateManageForm(request.POST or None, instance=template)
    if request.method == "POST" and form.is_valid():
        template = form.save()
        form.save_items(template)
        messages.success(request, "处方模板已更新。")
        return redirect("prescription_template_list")
    return render(
        request,
        "followup/reference_form.html",
        {
            "page_title": "编辑处方模板",
            "form": form,
            "cancel_url": reverse("prescription_template_list"),
            "submit_label": "保存处方模板",
        },
    )


@login_required
def prescription_template_delete(request, pk):
    denied = _ensure_reference_permission(request)
    if denied:
        return denied
    template = get_object_or_404(PrescriptionTemplate, pk=pk)
    if request.method == "POST":
        template.delete()
        messages.success(request, "处方模板已删除。")
        return redirect("prescription_template_list")
    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除处方模板",
            "description": f"将删除处方模板“{template.name}”及其条目，此操作不可恢复。",
            "cancel_url": reverse("prescription_template_list"),
        },
    )


@login_required
def account_create(request):
    if not can_manage_accounts(request.user):
        return _redirect_with_error(request, "只有 Root 可以创建账号。", "patient_list")

    form = AccountCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"账号 {user.username} 已创建。")
        return redirect("account_list")

    return render(
        request,
        "followup/account_form.html",
        {
            "page_title": "新建账号",
            "form": form,
            "submit_label": "创建账号",
            "cancel_url": reverse("account_list"),
        },
    )


@login_required
def account_update(request, pk):
    if not can_manage_accounts(request.user):
        return _redirect_with_error(request, "只有 Root 可以编辑账号。", "patient_list")

    target_user = get_object_or_404(User.objects.select_related("profile"), pk=pk)
    profile = get_user_profile(target_user)
    if profile.role == UserProfile.ROLE_ROOT:
        return _redirect_with_error(request, "Root 账号不能在页面中编辑。", "account_list")

    form = AccountUpdateForm(request.POST or None, instance=target_user, profile=profile)
    if request.method == "POST" and form.is_valid():
        updated_user = form.save()
        messages.success(request, f"账号 {updated_user.username} 已更新。")
        return redirect("account_list")

    return render(
        request,
        "followup/account_form.html",
        {
            "page_title": "编辑账号",
            "form": form,
            "submit_label": "保存修改",
            "cancel_url": reverse("account_list"),
        },
    )


@login_required
def account_delete(request, pk):
    if not can_manage_accounts(request.user):
        return _redirect_with_error(request, "只有 Root 可以删除账号。", "patient_list")

    target_user = get_object_or_404(User.objects.select_related("profile"), pk=pk)
    profile = get_user_profile(target_user)
    if profile.role == UserProfile.ROLE_ROOT or target_user.pk == request.user.pk:
        return _redirect_with_error(request, "当前账号不能在页面中删除。", "account_list")

    if request.method == "POST":
        username = target_user.username
        target_user.delete()
        messages.success(request, f"账号 {username} 已删除。")
        return redirect("account_list")

    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除账号",
            "description": f"将删除账号“{target_user.username}”，此操作不可恢复。",
            "cancel_url": reverse("account_list"),
        },
    )


@login_required
def project_list(request):
    denied = _ensure_project_module_permission(request)
    if denied:
        return denied
    projects_qs = get_project_queryset_for_user(
        request.user,
        ResearchProject.objects.annotate(
            enrollment_count_value=Count("enrollments", distinct=True),
        ),
    ).order_by("-created_at")
    projects = list(projects_qs)
    allowed_project_ids = {item.id for item in projects}
    enrollment_form = ProjectEnrollmentBatchForm(request.POST or None, initial={"enrollment_date": timezone.localdate()})
    selected_project_id = (request.POST.get("project_id") or request.GET.get("project_id") or "").strip()
    selected_project = None
    if selected_project_id.isdigit():
        selected_project = next((item for item in projects if item.id == int(selected_project_id)), None)
    enrollment_keyword = (request.GET.get("enroll_q") or request.POST.get("enroll_q") or "").strip()
    enrollment_tcm_disease = (request.GET.get("enroll_tcm_disease") or "").strip()
    enrollment_status = (request.GET.get("enroll_status") or "").strip()
    enrollment_start_date_from = (request.GET.get("enroll_start_date_from") or "").strip()
    enrollment_start_date_to = (request.GET.get("enroll_start_date_to") or "").strip()
    enrollment_ordering = (request.GET.get("enroll_ordering") or "-patient_id").strip()
    start_date_from = None
    start_date_to = None
    if enrollment_start_date_from:
        try:
            start_date_from = date.fromisoformat(enrollment_start_date_from)
        except ValueError:
            start_date_from = None
    if enrollment_start_date_to:
        try:
            start_date_to = date.fromisoformat(enrollment_start_date_to)
        except ValueError:
            start_date_to = None
    current_signature = _patient_row_cache_signature()
    view_cache_key = (
        "project_enrollment_rows",
        current_signature,
        tuple(sorted(allowed_project_ids)),
        selected_project.id if selected_project else 0,
        enrollment_keyword,
        enrollment_tcm_disease,
        enrollment_status,
        enrollment_start_date_from,
        enrollment_start_date_to,
        enrollment_ordering,
    )
    cached_view_rows = _cache_get(_PROJECT_ENROLLMENT_VIEW_CACHE, view_cache_key)
    if cached_view_rows is not None:
        enrollment_rows = _clone_rows(cached_view_rows)
    else:
        base_cache_key = ("project_enrollment_base_rows", current_signature)
        cached_base_rows = _cache_get(_PROJECT_ENROLLMENT_BASE_CACHE, base_cache_key)
        if cached_base_rows is None:
            enrollment_rows = _build_patient_rows(cache_signature=base_cache_key[1])
            _cache_set(_PROJECT_ENROLLMENT_BASE_CACHE, base_cache_key, enrollment_rows)
        else:
            enrollment_rows = _clone_rows(cached_base_rows)
        enrolled_group_by_patient_id = {}
        if selected_project:
            enrollment_records = list(selected_project.enrollments.all())
            enrolled_group_by_patient_id = {item.patient_id: (item.group_name or "") for item in enrollment_records}
        if enrollment_keyword:
            keyword = enrollment_keyword.lower()
            filtered_rows = []
            for row in enrollment_rows:
                visible_project_tags = [
                    tag
                    for tag in row.get("project_tags", [])
                    if tag.get("project_id") in allowed_project_ids
                ]
                patient = row["patient"]
                project_names = " ".join((tag.get("project_name") or "") for tag in visible_project_tags)
                group_names = " ".join((tag.get("group_name") or "") for tag in visible_project_tags)
                haystacks = [
                    patient.outpatient_number,
                    patient.patient_id,
                    patient.name,
                    patient.phone,
                    patient.ethnicity,
                    row.get("visit_unit") or "",
                    row.get("tcm_disease") or "",
                    row.get("western_disease") or "",
                    row.get("status") or "",
                    project_names,
                    group_names,
                ]
                if any(keyword in str(item).lower() for item in haystacks):
                    filtered_rows.append(row)
            enrollment_rows = filtered_rows
        if enrollment_tcm_disease:
            keyword = enrollment_tcm_disease.lower()
            enrollment_rows = [
                row for row in enrollment_rows if keyword in str(row.get("tcm_disease") or "").lower()
            ]
        normalized_rows = []
        for row in enrollment_rows:
            patient_id = row["patient"].id
            project_tags = [
                tag
                for tag in list(row.get("project_tags", []))
                if tag.get("project_id") in allowed_project_ids
            ]
            is_enrolled = bool(project_tags)
            row["enrollment_status"] = "已纳入" if is_enrolled else "未纳入"
            row["enrollment_status_value"] = "enrolled" if is_enrolled else "not_enrolled"
            row["selected_project_group"] = enrolled_group_by_patient_id.get(patient_id, "")
            if selected_project:
                project_tags.sort(
                    key=lambda tag: (
                        0 if tag.get("project_id") == selected_project.id else 1,
                        str(tag.get("project_name") or ""),
                    )
                )
            row["project_tags"] = project_tags
            row["project_tags_display"] = project_tags
            normalized_rows.append(row)
        enrollment_rows = normalized_rows
        if enrollment_status in {"enrolled", "not_enrolled"}:
            enrollment_rows = [
                row for row in enrollment_rows if row.get("enrollment_status_value") == enrollment_status
            ]
        if start_date_from:
            enrollment_rows = [
                row for row in enrollment_rows if row.get("start_date") and row.get("start_date") >= start_date_from
            ]
        if start_date_to:
            enrollment_rows = [
                row for row in enrollment_rows if row.get("start_date") and row.get("start_date") <= start_date_to
            ]

        enroll_sort_map = {
            "patient_id": lambda item: item["patient"].outpatient_number or "",
            "-patient_id": lambda item: item["patient"].outpatient_number or "",
            "name": lambda item: item["patient"].name or "",
            "-name": lambda item: item["patient"].name or "",
            "age": lambda item: item["patient"].current_age or -1,
            "-age": lambda item: item["patient"].current_age or -1,
            "ethnicity": lambda item: item["patient"].ethnicity or "",
            "-ethnicity": lambda item: item["patient"].ethnicity or "",
            "tcm_disease": lambda item: item.get("tcm_disease") or "",
            "-tcm_disease": lambda item: item.get("tcm_disease") or "",
            "western_disease": lambda item: item.get("western_disease") or "",
            "-western_disease": lambda item: item.get("western_disease") or "",
            "visit_unit": lambda item: item.get("visit_unit") or "",
            "-visit_unit": lambda item: item.get("visit_unit") or "",
            "project": lambda item: " ".join((tag.get("project_name") or "") for tag in item.get("project_tags", [])),
            "-project": lambda item: " ".join((tag.get("project_name") or "") for tag in item.get("project_tags", [])),
            "group": lambda item: (item.get("selected_project_group") or " ".join((tag.get("group_name") or "") for tag in item.get("project_tags", []))),
            "-group": lambda item: (item.get("selected_project_group") or " ".join((tag.get("group_name") or "") for tag in item.get("project_tags", []))),
            "enrollment_status": lambda item: item.get("enrollment_status") or "",
            "-enrollment_status": lambda item: item.get("enrollment_status") or "",
        }
        if enrollment_ordering not in enroll_sort_map:
            enrollment_ordering = "-patient_id"
        enrollment_rows = sorted(
            enrollment_rows,
            key=enroll_sort_map[enrollment_ordering],
            reverse=enrollment_ordering.startswith("-"),
        )
        _cache_set(_PROJECT_ENROLLMENT_VIEW_CACHE, view_cache_key, enrollment_rows)

    sort_query = request.GET.copy()
    sort_query.pop("enroll_page", None)
    sort_query.pop("enroll_ordering", None)

    def _enroll_sort_query(field_name):
        query = sort_query.copy()
        if enrollment_ordering == field_name:
            query["enroll_ordering"] = f"-{field_name}"
        elif enrollment_ordering == f"-{field_name}":
            query["enroll_ordering"] = field_name
        else:
            query["enroll_ordering"] = field_name
        return query.urlencode()

    enroll_sort_queries = {
        "patient_id": _enroll_sort_query("patient_id"),
        "name": _enroll_sort_query("name"),
        "age": _enroll_sort_query("age"),
        "ethnicity": _enroll_sort_query("ethnicity"),
        "tcm_disease": _enroll_sort_query("tcm_disease"),
        "western_disease": _enroll_sort_query("western_disease"),
        "visit_unit": _enroll_sort_query("visit_unit"),
        "project": _enroll_sort_query("project"),
        "group": _enroll_sort_query("group"),
        "enrollment_status": _enroll_sort_query("enrollment_status"),
    }
    enroll_paginator = Paginator(enrollment_rows, 10)
    enroll_page_number = request.GET.get("enroll_page")
    enrollment_page_obj = enroll_paginator.get_page(enroll_page_number)
    enroll_query_base = request.GET.copy()
    enroll_query_base.pop("enroll_page", None)
    enroll_prev_query = None
    enroll_next_query = None
    if enrollment_page_obj.has_previous():
        query = enroll_query_base.copy()
        query["enroll_page"] = enrollment_page_obj.previous_page_number()
        enroll_prev_query = query.urlencode()
    if enrollment_page_obj.has_next():
        query = enroll_query_base.copy()
        query["enroll_page"] = enrollment_page_obj.next_page_number()
        enroll_next_query = query.urlencode()

    if request.method == "POST" and request.POST.get("action") == "add_patients" and enrollment_form.is_valid():
        selected_ids = [int(item) for item in request.POST.getlist("selected_patient_ids") if item.isdigit()]
        if not selected_project:
            messages.error(request, "请先选择项目。")
        elif not selected_ids:
            messages.error(request, "请至少选择 1 位患者后再纳入项目。")
        else:
            group_name = (enrollment_form.cleaned_data.get("group_name") or "").strip()
            enrollment_date = enrollment_form.cleaned_data.get("enrollment_date") or timezone.localdate()
            notes = (enrollment_form.cleaned_data.get("notes") or "").strip()
            created_count = 0
            skipped_count = 0
            for patient in Patient.objects.filter(pk__in=selected_ids):
                if not can_modify_record(request.user, patient):
                    skipped_count += 1
                    continue
                _, created = ProjectEnrollment.objects.get_or_create(
                    project=selected_project,
                    patient=patient,
                    defaults={
                        "group_name": group_name,
                        "enrollment_date": enrollment_date,
                        "notes": notes,
                        "created_by": request.user,
                    },
                )
                if created:
                    created_count += 1
            if created_count:
                messages.success(request, f"已纳入 {created_count} 位患者。")
            else:
                messages.info(request, "所选患者已在当前项目中。")
            if skipped_count:
                messages.warning(request, f"有 {skipped_count} 位患者超出历史操作期限，未执行纳入。")
        query_data = {}
        if selected_project_id:
            query_data["project_id"] = selected_project_id
        if enrollment_keyword:
            query_data["enroll_q"] = enrollment_keyword
        if enrollment_tcm_disease:
            query_data["enroll_tcm_disease"] = enrollment_tcm_disease
        if enrollment_status:
            query_data["enroll_status"] = enrollment_status
        if enrollment_start_date_from:
            query_data["enroll_start_date_from"] = enrollment_start_date_from
        if enrollment_start_date_to:
            query_data["enroll_start_date_to"] = enrollment_start_date_to
        if enrollment_ordering:
            query_data["enroll_ordering"] = enrollment_ordering
        query = urlencode(query_data) if query_data else ""
        return redirect(f"{reverse('project_list')}?{query}" if query else reverse("project_list"))

    return render(
        request,
        "followup/project_list.html",
        {
            "app_name": settings.APP_NAME,
            "projects": projects,
            "can_manage_project_definition": can_manage_project_definition(request.user),
            "enrollment_form": enrollment_form,
            "enrollment_project_id": selected_project_id,
            "enrollment_project": selected_project,
            "enrollment_page_obj": enrollment_page_obj,
            "enrollment_keyword": enrollment_keyword,
            "enrollment_tcm_disease": enrollment_tcm_disease,
            "enrollment_status": enrollment_status,
            "enrollment_start_date_from": enrollment_start_date_from,
            "enrollment_start_date_to": enrollment_start_date_to,
            "enrollment_ordering": enrollment_ordering,
            "enroll_sort_queries": enroll_sort_queries,
            "enroll_prev_query": enroll_prev_query,
            "enroll_next_query": enroll_next_query,
        },
    )


@login_required
def project_create(request):
    denied = _ensure_project_definition_permission(request)
    if denied:
        return denied
    form = ResearchProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.created_by = request.user
        project.save()
        messages.success(request, "项目已创建。")
        return redirect("project_detail", pk=project.pk)
    return render(
        request,
        "followup/project_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "新建项目",
            "submit_label": "保存项目",
            "form": form,
            "cancel_url": reverse("project_list"),
        },
    )


@login_required
def project_update(request, pk):
    denied = _ensure_project_definition_permission(request)
    if denied:
        return denied
    project = get_object_or_404(ResearchProject, pk=pk)
    form = ResearchProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "项目信息已更新。")
        return redirect("project_detail", pk=project.pk)
    return render(
        request,
        "followup/project_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "编辑项目",
            "submit_label": "保存修改",
            "form": form,
            "cancel_url": reverse("project_detail", args=[project.pk]),
        },
    )


@login_required
def project_delete(request, pk):
    denied = _ensure_project_definition_permission(request)
    if denied:
        return denied
    project = get_object_or_404(ResearchProject, pk=pk)
    if request.method == "POST":
        name = project.name
        project.delete()
        messages.success(request, f"项目“{name}”已删除。")
        return redirect("project_list")
    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除项目",
            "description": f"将删除项目“{project.name}”及其入组关联，此操作不可恢复。",
            "cancel_url": reverse("project_detail", args=[project.pk]),
        },
    )


@login_required
def project_detail(request, pk):
    denied = _ensure_project_module_permission(request)
    if denied:
        return denied
    project_queryset = get_project_queryset_for_user(
        request.user,
        ResearchProject.objects.annotate(
            enrollment_count_value=Count("enrollments", distinct=True),
        ).prefetch_related("enrollments__patient"),
    )
    project = get_object_or_404(
        project_queryset,
        pk=pk,
    )
    project_ordering = (request.GET.get("project_ordering") or "name").strip()
    visible_project_ids = set(
        get_project_queryset_for_user(request.user, ResearchProject.objects.all()).values_list("id", flat=True)
    )
    project_rows = _get_project_rows(project, visible_project_ids=visible_project_ids)
    allowed_project_orderings = {
        "name",
        "-name",
        "age",
        "-age",
        "ethnicity",
        "-ethnicity",
        "tcm_disease",
        "-tcm_disease",
        "western_disease",
        "-western_disease",
        "project",
        "-project",
        "group",
        "-group",
        "marker",
        "-marker",
        "next_followup_date",
        "-next_followup_date",
        "status",
        "-status",
    }
    if project_ordering not in allowed_project_orderings:
        project_ordering = "name"
    project_rows = _sort_project_rows(project_rows, project_ordering)
    for row in project_rows:
        enrollment_obj = row.get("current_enrollment_obj")
        row["can_manage_enrollment"] = bool(enrollment_obj and can_modify_record(request.user, enrollment_obj))
    project_stats = _build_dashboard_stats(project_rows)
    project_group_marker_stats = _build_project_group_marker_stats(project)
    paginator = Paginator(project_rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    prev_page_query = _encode_query(request, page=page_obj.previous_page_number()) if page_obj.has_previous() else ""
    next_page_query = _encode_query(request, page=page_obj.next_page_number()) if page_obj.has_next() else ""
    sort_query_base = request.GET.copy()
    sort_query_base.pop("project_ordering", None)
    sort_query_base.pop("page", None)

    def _project_sort_query(field_name):
        query = sort_query_base.copy()
        if project_ordering == field_name:
            query["project_ordering"] = f"-{field_name}"
        elif project_ordering == f"-{field_name}":
            query["project_ordering"] = field_name
        else:
            query["project_ordering"] = field_name
        return query.urlencode()

    return render(
        request,
        "followup/project_detail.html",
        {
            "app_name": settings.APP_NAME,
            "project": project,
            "enrollment_gap": max((project.target_enrollment or 0) - (project.enrollment_count_value or 0), 0),
            "project_stats": project_stats,
            "project_group_marker_stats": project_group_marker_stats,
            "page_obj": page_obj,
            "prev_page_query": prev_page_query,
            "next_page_query": next_page_query,
            "current_query": request.GET.urlencode(),
            "can_manage_project_definition": can_manage_project_definition(request.user),
            "can_export_project_data": can_export_project_data(request.user),
            "project_sort_queries": {
                "name": _project_sort_query("name"),
                "age": _project_sort_query("age"),
                "ethnicity": _project_sort_query("ethnicity"),
                "tcm_disease": _project_sort_query("tcm_disease"),
                "western_disease": _project_sort_query("western_disease"),
                "project": _project_sort_query("project"),
                "group": _project_sort_query("group"),
                "marker": _project_sort_query("marker"),
                "next_followup_date": _project_sort_query("next_followup_date"),
                "status": _project_sort_query("status"),
            },
            "marker_status_choices": ProjectEnrollment.MARKER_CHOICES,
        },
    )


@login_required
def project_enrollment_delete(request, pk, enrollment_id):
    denied = _ensure_project_module_permission(request)
    if denied:
        return denied
    project = get_object_or_404(get_project_queryset_for_user(request.user, ResearchProject.objects.all()), pk=pk)
    enrollment = get_object_or_404(ProjectEnrollment.objects.select_related("patient"), pk=enrollment_id, project=project)
    denied = _ensure_modify_permission(request, enrollment, "project_detail", project.pk)
    if denied:
        return denied

    if request.method == "POST":
        patient_name = enrollment.patient.name
        enrollment.delete()
        messages.success(request, f"已将患者“{patient_name}”移出项目。")
        return redirect("project_detail", pk=project.pk)

    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "移出项目",
            "description": f"将把患者“{enrollment.patient.name}”从项目“{project.name}”移出，确认继续？",
            "cancel_url": reverse("project_detail", args=[project.pk]),
        },
    )


@login_required
def project_enrollment_marker_update(request, pk, enrollment_id):
    denied = _ensure_project_module_permission(request)
    if denied:
        return denied
    project = get_object_or_404(get_project_queryset_for_user(request.user, ResearchProject.objects.all()), pk=pk)
    enrollment = get_object_or_404(
        ProjectEnrollment.objects.select_related("patient"),
        pk=enrollment_id,
        project=project,
    )
    denied = _ensure_modify_permission(request, enrollment, "project_detail", project.pk)
    if denied:
        return denied
    if request.method == "POST":
        form = ProjectEnrollmentMarkerForm(request.POST, instance=enrollment)
        if form.is_valid():
            marker = form.save(commit=False)
            marker.marker_by = request.user
            marker.marker_updated_at = timezone.now()
            marker.save()
            messages.success(request, "患者项目标记已更新。")
            return redirect("project_detail", pk=project.pk)
        error_messages = []
        for _, errors in form.errors.items():
            for error in errors:
                text = str(error).strip()
                if text:
                    error_messages.append(text)
        if error_messages:
            messages.error(request, "；".join(error_messages))
        else:
            messages.error(request, "标记保存失败，请检查后重试。")
        return redirect("project_detail", pk=project.pk)

    messages.info(request, "请在项目详情页通过“标记”按钮进行编辑。")
    return redirect("project_detail", pk=project.pk)


def _build_patient_rows(patient_queryset=None, cache_signature=None):
    if patient_queryset is None:
        signature = cache_signature or _patient_row_cache_signature()
        cache_key = ("all", signature)
        cached_rows = _cache_get(_PATIENT_ROW_CACHE, cache_key)
        if cached_rows is not None:
            return _clone_rows(cached_rows)

    base_queryset = patient_queryset if patient_queryset is not None else Patient.objects.all()
    latest_treatment_queryset = Treatment.objects.filter(patient=OuterRef("pk")).order_by("-start_date", "-created_at")
    enrollments_prefetch = Prefetch(
        "project_enrollments",
        queryset=ProjectEnrollment.objects.select_related("project").only(
            "id",
            "patient_id",
            "project_id",
            "group_name",
            "marker_status",
            "project__name",
            "project__status",
        ),
    )
    patients = list(
        base_queryset.only(
            "id",
            "patient_id",
            "outpatient_number",
            "name",
            "gender",
            "birth_date",
            "age",
            "ethnicity",
            "phone",
            "address",
            "diagnosis",
            "group_name",
        )
        .prefetch_related(enrollments_prefetch)
        .annotate(
            treatment_count_value=Count("treatments", distinct=True),
            followup_count_value=Count("treatments__followups", distinct=True),
            latest_treatment_id=Subquery(latest_treatment_queryset.values("id")[:1]),
            latest_treatment_name=Subquery(latest_treatment_queryset.values("treatment_name")[:1]),
            latest_treatment_chief_complaint=Subquery(latest_treatment_queryset.values("chief_complaint")[:1]),
            latest_treatment_start_date=Subquery(latest_treatment_queryset.values("start_date")[:1]),
            latest_treatment_admission_date=Subquery(latest_treatment_queryset.values("admission_date")[:1]),
            latest_treatment_discharge_date=Subquery(latest_treatment_queryset.values("discharge_date")[:1]),
            latest_treatment_group_name=Subquery(latest_treatment_queryset.values("group_name")[:1]),
            latest_treatment_tcm_disease=Subquery(latest_treatment_queryset.values("tcm_disease")[:1]),
            latest_treatment_western_disease=Subquery(latest_treatment_queryset.values("western_disease")[:1]),
            latest_treatment_total_weeks=Subquery(latest_treatment_queryset.values("total_weeks")[:1]),
            latest_treatment_followup_interval_days=Subquery(
                latest_treatment_queryset.values("followup_interval_days")[:1]
            ),
            latest_treatment_followup_closed=Subquery(latest_treatment_queryset.values("followup_closed")[:1]),
        )
    )
    latest_treatment_ids = [item.latest_treatment_id for item in patients if item.latest_treatment_id]
    latest_treatment_followup_map = {}
    if latest_treatment_ids:
        latest_followup_queryset = FollowUp.objects.filter(treatment_id=OuterRef("pk")).order_by(
            "-visit_number",
            "-followup_date",
            "-id",
        )
        treatment_followup_metrics = (
            Treatment.objects.filter(id__in=latest_treatment_ids)
            .annotate(
                latest_followup_count=Count("followups"),
                latest_followup_date=Subquery(latest_followup_queryset.values("followup_date")[:1]),
                latest_followup_planned_next_date=Subquery(
                    latest_followup_queryset.values("planned_next_followup_date")[:1]
                ),
            )
            .values(
                "id",
                "latest_followup_count",
                "latest_followup_date",
                "latest_followup_planned_next_date",
            )
        )
        latest_treatment_followup_map = {
            item["id"]: {
                "count": item["latest_followup_count"] or 0,
                "followup_date": item["latest_followup_date"],
                "planned_next_followup_date": item["latest_followup_planned_next_date"],
            }
            for item in treatment_followup_metrics
        }

    today = timezone.localdate()
    rows = []
    for patient in patients:
        treatment_id = patient.latest_treatment_id
        treatment = None
        status = STATUS_NOT_STARTED
        start_date = None
        next_followup_date = None
        progress_percent = 0
        completed_count = 0
        planned_count = 0
        visit_unit = patient.group_name
        tcm_disease = ""
        western_disease = patient.diagnosis
        if treatment_id:
            treatment = SimpleNamespace(
                id=treatment_id,
                treatment_name=patient.latest_treatment_name or "",
                chief_complaint=patient.latest_treatment_chief_complaint or "",
                admission_date=patient.latest_treatment_admission_date,
                discharge_date=patient.latest_treatment_discharge_date,
            )
            start_date = patient.latest_treatment_start_date
            visit_unit = patient.latest_treatment_group_name or patient.group_name
            tcm_disease = patient.latest_treatment_tcm_disease or ""
            western_disease = patient.latest_treatment_western_disease or patient.diagnosis
            followup_interval_days = int(patient.latest_treatment_followup_interval_days or 0)
            total_weeks = int(patient.latest_treatment_total_weeks or 0)
            followup_closed = bool(patient.latest_treatment_followup_closed)
            planned_count = (
                max(1, (total_weeks * 7) // followup_interval_days)
                if followup_interval_days > 0 and total_weeks > 0
                else 0
            )
            treatment_followup_metrics = latest_treatment_followup_map.get(treatment_id, {})
            completed_count = int(treatment_followup_metrics.get("count") or 0)
            latest_followup_date = treatment_followup_metrics.get("followup_date")
            latest_planned_next_followup_date = treatment_followup_metrics.get("planned_next_followup_date")
            if followup_closed or planned_count == 0 or completed_count >= planned_count:
                next_followup_date = None
            elif latest_followup_date:
                next_followup_date = latest_planned_next_followup_date or (
                    latest_followup_date + timedelta(days=followup_interval_days)
                )
            elif start_date:
                next_followup_date = start_date + timedelta(days=followup_interval_days)

            progress_percent = min(100, int(completed_count / planned_count * 100)) if planned_count else 0
            if followup_closed or (planned_count and completed_count >= planned_count):
                status = STATUS_DONE
            elif next_followup_date and next_followup_date < today:
                status = STATUS_OVERDUE
            elif next_followup_date and next_followup_date == today:
                status = STATUS_TODAY
            else:
                status = STATUS_ACTIVE

        project_tags = []
        seen_project_ids = set()
        for enrollment in patient.project_enrollments.all():
            if enrollment.project_id in seen_project_ids:
                continue
            seen_project_ids.add(enrollment.project_id)
            project_tags.append(
                {
                    "project_id": enrollment.project_id,
                    "project_name": enrollment.project.name,
                    "group_name": enrollment.group_name or "",
                    "marker_status": enrollment.marker_status or "",
                    "project_status": enrollment.project.status,
                }
            )
        rows.append(
            {
                "patient": patient,
                "treatment": treatment,
                "visit_unit": visit_unit,
                "tcm_disease": tcm_disease,
                "western_disease": western_disease,
                "status": status,
                "start_date": start_date,
                "next_followup_date": next_followup_date,
                "progress_percent": progress_percent,
                "completed_count": completed_count,
                "planned_count": planned_count,
                "treatment_count": getattr(patient, "treatment_count_value", 0),
                "followup_count": getattr(patient, "followup_count_value", 0),
                "project_tags": project_tags,
            }
        )
    if patient_queryset is None:
        _cache_set(_PATIENT_ROW_CACHE, cache_key, rows)
    return _clone_rows(rows) if patient_queryset is None else rows


def _get_project_rows(project, visible_project_ids=None):
    enrollment_map = {
        item.patient_id: item
        for item in project.enrollments.select_related("marker_by").all()
    }
    project_patient_ids = set(project.enrollments.values_list("patient_id", flat=True))
    project_patients = Patient.objects.filter(id__in=project_patient_ids)
    rows = _build_patient_rows(project_patients)
    rows = _sort_rows(rows, "next_followup_date")
    for row in rows:
        visible_tags = [
            tag
            for tag in row.get("project_tags", [])
            if visible_project_ids is None or tag.get("project_id") in visible_project_ids
        ]
        project_tags_view = [
            {
                **tag,
                "is_current_project": tag.get("project_id") == project.id,
            }
            for tag in visible_tags
        ]
        project_tags_view.sort(
            key=lambda tag: (
                0 if tag.get("is_current_project") else 1,
                str(tag.get("project_name") or ""),
            )
        )
        row["project_tags_view"] = project_tags_view
        row["all_project_names"] = " ".join((tag.get("project_name") or "") for tag in project_tags_view)
        row["all_group_names"] = " ".join((tag.get("group_name") or "") for tag in project_tags_view)
        enrollment = enrollment_map.get(row["patient"].id)
        row["current_enrollment_id"] = enrollment.id if enrollment else None
        row["current_enrollment_obj"] = enrollment
        marker_value = _normalize_project_marker_status(enrollment.marker_status if enrollment else "")
        row["marker_status_value"] = marker_value
        row["marker_status_label"] = _project_marker_label(marker_value)
        row["marker_date"] = enrollment.marker_date if enrollment else None
        row["marker_note"] = enrollment.marker_note if enrollment else ""
        row["marker_by"] = _display_user_name(enrollment.marker_by) if enrollment else ""
        row["marker_updated_at"] = _display_datetime(enrollment.marker_updated_at) if enrollment else ""
    return rows


def _sort_project_rows(rows, ordering):
    status_order = {
        STATUS_OVERDUE: 0,
        STATUS_TODAY: 1,
        STATUS_ACTIVE: 2,
        STATUS_DONE: 3,
        STATUS_NOT_STARTED: 4,
    }
    sort_map = {
        "name": lambda item: item["patient"].name or "",
        "-name": lambda item: item["patient"].name or "",
        "age": lambda item: item["patient"].current_age or -1,
        "-age": lambda item: item["patient"].current_age or -1,
        "ethnicity": lambda item: item["patient"].ethnicity or "",
        "-ethnicity": lambda item: item["patient"].ethnicity or "",
        "tcm_disease": lambda item: item.get("tcm_disease") or "",
        "-tcm_disease": lambda item: item.get("tcm_disease") or "",
        "western_disease": lambda item: item.get("western_disease") or "",
        "-western_disease": lambda item: item.get("western_disease") or "",
        "project": lambda item: item.get("all_project_names") or "",
        "-project": lambda item: item.get("all_project_names") or "",
        "group": lambda item: item.get("all_group_names") or "",
        "-group": lambda item: item.get("all_group_names") or "",
        "marker": lambda item: item.get("marker_status_label") or "",
        "-marker": lambda item: item.get("marker_status_label") or "",
        "next_followup_date": lambda item: item.get("next_followup_date") or date.max,
        "-next_followup_date": lambda item: item.get("next_followup_date") or date.max,
        "status": lambda item: status_order.get(item.get("status"), 99),
        "-status": lambda item: status_order.get(item.get("status"), 99),
    }
    key = sort_map.get(ordering, sort_map["name"])
    return sorted(rows, key=key, reverse=ordering.startswith("-"))


def _build_dashboard_stats(rows):
    today = timezone.localdate()
    week_end = today + timedelta(days=7)
    today_due = sum(1 for row in rows if row["next_followup_date"] == today)
    week_due = sum(
        1
        for row in rows
        if row["next_followup_date"] and today < row["next_followup_date"] <= week_end
    )
    marker_counts = {
        ProjectEnrollment.MARKER_IN: 0,
        ProjectEnrollment.MARKER_COMPLETED: 0,
        ProjectEnrollment.MARKER_WITHDRAWN: 0,
        ProjectEnrollment.MARKER_LOST: 0,
    }
    for row in rows:
        marker = _normalize_project_marker_status(row.get("marker_status_value"))
        marker_counts[marker] += 1
    return {
        "patient_count": len(rows),
        "treatment_count": sum(row["treatment_count"] for row in rows),
        "followup_count": sum(row["followup_count"] for row in rows),
        "today_due": today_due,
        "week_due": week_due,
        "marker_counts": marker_counts,
        "marker_in_count": marker_counts[ProjectEnrollment.MARKER_IN],
        "marker_completed_count": marker_counts[ProjectEnrollment.MARKER_COMPLETED],
        "marker_withdrawn_count": marker_counts[ProjectEnrollment.MARKER_WITHDRAWN],
        "marker_lost_count": marker_counts[ProjectEnrollment.MARKER_LOST],
    }


def _get_cached_dashboard_stats(rows, signature):
    cache_key = ("patient_stats", signature)
    cached = _cache_get(_PATIENT_STATS_CACHE, cache_key)
    if cached is not None:
        return dict(cached)
    stats = _build_dashboard_stats(rows)
    _cache_set(_PATIENT_STATS_CACHE, cache_key, dict(stats))
    return stats


def _build_project_group_marker_stats(project):
    grouped = {}
    for enrollment in project.enrollments.all():
        group_name = (enrollment.group_name or "").strip() or "未分组"
        marker = _normalize_project_marker_status(enrollment.marker_status)
        row = grouped.setdefault(
            group_name,
            {
                "group_name": group_name,
                "in_count": 0,
                "completed_count": 0,
                "withdrawn_count": 0,
                "lost_count": 0,
                "total_count": 0,
            },
        )
        if marker == ProjectEnrollment.MARKER_IN:
            row["in_count"] += 1
        elif marker == ProjectEnrollment.MARKER_COMPLETED:
            row["completed_count"] += 1
        elif marker == ProjectEnrollment.MARKER_WITHDRAWN:
            row["withdrawn_count"] += 1
        elif marker == ProjectEnrollment.MARKER_LOST:
            row["lost_count"] += 1
        row["total_count"] += 1
    return sorted(grouped.values(), key=lambda item: item["group_name"])


def _matches_filters(row, cleaned):
    patient = row["patient"]
    treatment = row["treatment"]

    keyword = (cleaned.get("q") or "").strip().lower()
    if keyword:
        project_haystacks = []
        for tag in row.get("project_tags", []):
            project_haystacks.append(tag.get("project_name") or "")
            project_haystacks.append(tag.get("group_name") or "")
        haystacks = [
            patient.outpatient_number,
            patient.patient_id,
            patient.name,
            patient.phone,
            patient.ethnicity,
            patient.address,
            row["visit_unit"],
            row["tcm_disease"],
            row["western_disease"],
            treatment.treatment_name if treatment else "",
            treatment.chief_complaint if treatment else "",
        ] + project_haystacks
        if not any(keyword in (item or "").lower() for item in haystacks):
            return False

    tcm_disease = (cleaned.get("tcm_disease") or "").strip().lower()
    if tcm_disease and tcm_disease not in (row["tcm_disease"] or "").lower():
        return False

    status = cleaned.get("status")
    if status == "today" and row["status"] != STATUS_TODAY:
        return False
    if status == "active" and row["status"] != STATUS_ACTIVE:
        return False
    if status == "done" and row["status"] != STATUS_DONE:
        return False
    if status == "overdue" and row["status"] != STATUS_OVERDUE:
        return False

    start_date_from = cleaned.get("start_date_from")
    if start_date_from and (not row["start_date"] or row["start_date"] < start_date_from):
        return False

    start_date_to = cleaned.get("start_date_to")
    if start_date_to and (not row["start_date"] or row["start_date"] > start_date_to):
        return False

    return True


def _sort_rows(rows, ordering):
    status_order = {
        STATUS_OVERDUE: 0,
        STATUS_TODAY: 1,
        STATUS_ACTIVE: 2,
        STATUS_DONE: 3,
        STATUS_NOT_STARTED: 4,
    }
    sort_map = {
        "patient_id": lambda item: item["patient"].outpatient_number or "",
        "-patient_id": lambda item: item["patient"].outpatient_number or "",
        "name": lambda item: item["patient"].name or "",
        "-name": lambda item: item["patient"].name or "",
        "age": lambda item: item["patient"].current_age or -1,
        "-age": lambda item: item["patient"].current_age or -1,
        "ethnicity": lambda item: item["patient"].ethnicity or "",
        "-ethnicity": lambda item: item["patient"].ethnicity or "",
        "tcm_disease": lambda item: item["tcm_disease"] or "",
        "-tcm_disease": lambda item: item["tcm_disease"] or "",
        "western_disease": lambda item: item["western_disease"] or "",
        "-western_disease": lambda item: item["western_disease"] or "",
        "treatment_count": lambda item: item["treatment_count"],
        "-treatment_count": lambda item: item["treatment_count"],
        "followup_count": lambda item: item["followup_count"],
        "-followup_count": lambda item: item["followup_count"],
        "start_date": lambda item: item["start_date"] or date.max,
        "-start_date": lambda item: item["start_date"] or date.min,
        "next_followup_date": lambda item: item["next_followup_date"] or date.max,
        "-next_followup_date": lambda item: item["next_followup_date"] or date.min,
        "status": lambda item: status_order.get(item["status"], 99),
        "-status": lambda item: status_order.get(item["status"], 99),
    }
    key = sort_map.get(ordering, sort_map["next_followup_date"])
    reverse = ordering.startswith("-")
    return sorted(rows, key=key, reverse=reverse)


def _filter_rows_by_visible_projects(rows, visible_project_ids):
    if visible_project_ids is None:
        return rows
    normalized_visible_ids = set(visible_project_ids)
    filtered_rows = []
    for row in rows:
        visible_tags = [
            tag
            for tag in row.get("project_tags", [])
            if tag.get("project_id") in normalized_visible_ids
        ]
        row_copy = dict(row)
        row_copy["project_tags"] = visible_tags
        filtered_rows.append(row_copy)
    return filtered_rows


def _get_visible_project_ids_for_user(user):
    if get_user_role(user) == UserProfile.ROLE_ROOT:
        return None
    return set(
        get_project_queryset_for_user(user, ResearchProject.objects.all()).values_list("id", flat=True)
    )


def _get_filtered_rows(data, visible_project_ids=None):
    data_signature = _patient_row_cache_signature()
    visible_key = (
        "__all__"
        if visible_project_ids is None
        else tuple(sorted(int(item) for item in set(visible_project_ids)))
    )
    cache_key = (
        data_signature,
        visible_key,
        str((data or {}).get("q") or "").strip(),
        str((data or {}).get("tcm_disease") or "").strip(),
        str((data or {}).get("status") or "").strip(),
        str((data or {}).get("start_date_from") or "").strip(),
        str((data or {}).get("start_date_to") or "").strip(),
        str((data or {}).get("ordering") or "next_followup_date").strip(),
    )
    cached = _cache_get(_PATIENT_FILTER_CACHE, cache_key)
    if cached is not None:
        form = PatientFilterForm(data or None)
        form.is_valid()
        cleaned = getattr(form, "cleaned_data", {})
        return form, _clone_rows(cached["rows"]), cleaned, _clone_rows(cached["all_rows"]), data_signature

    form = PatientFilterForm(data or None)
    form.is_valid()
    cleaned = getattr(form, "cleaned_data", {})
    all_rows = _filter_rows_by_visible_projects(
        _build_patient_rows(cache_signature=data_signature),
        visible_project_ids,
    )
    rows = [row for row in all_rows if _matches_filters(row, cleaned)]
    ordering = (data or {}).get("ordering") or "next_followup_date"
    allowed_orderings = {
        "patient_id",
        "-patient_id",
        "name",
        "-name",
        "age",
        "-age",
        "ethnicity",
        "-ethnicity",
        "tcm_disease",
        "-tcm_disease",
        "western_disease",
        "-western_disease",
        "treatment_count",
        "-treatment_count",
        "followup_count",
        "-followup_count",
        "start_date",
        "-start_date",
        "next_followup_date",
        "-next_followup_date",
        "status",
        "-status",
    }
    if ordering not in allowed_orderings:
        ordering = "next_followup_date"
    rows = _sort_rows(rows, ordering)
    _cache_set(
        _PATIENT_FILTER_CACHE,
        cache_key,
        {"rows": rows, "all_rows": all_rows},
    )
    return form, rows, cleaned, all_rows, data_signature


def _encode_query(request, **updates):
    query = request.GET.copy()
    for key, value in updates.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()


def _get_export_rows(request):
    raw_query = request.POST.get("current_query", "")
    query_data = QueryDict(raw_query, mutable=False)
    visible_project_ids = _get_visible_project_ids_for_user(request.user)
    _, rows, _, _, _ = _get_filtered_rows(query_data, visible_project_ids=visible_project_ids)
    selected_ids = {int(item) for item in request.POST.getlist("selected_ids") if item.isdigit()}
    scope = request.POST.get("scope", "selected")
    if scope == "selected":
        if not selected_ids:
            return []
        rows = [row for row in rows if row["patient"].id in selected_ids]
    return rows


def _get_project_export_rows(request, project, visible_project_ids=None):
    rows = _get_project_rows(project, visible_project_ids=visible_project_ids)
    selected_ids = {int(item) for item in request.POST.getlist("selected_ids") if item.isdigit()}
    scope = request.POST.get("scope", "selected")
    if scope == "selected":
        if not selected_ids:
            return []
        rows = [row for row in rows if row["patient"].id in selected_ids]
    return rows


def _csv_bytes(headers, values):
    text_stream = io.StringIO()
    writer = csv.writer(text_stream)
    writer.writerow(headers)
    for row in values:
        writer.writerow(row)
    return text_stream.getvalue().encode("utf-8-sig")


def _display_user_name(user):
    if not user:
        return ""
    return (user.first_name or user.username or "").strip()


def _display_datetime(dt):
    if not dt:
        return ""
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")


MAX_AUXILIARY_FILE_SIZE = 5 * 1024 * 1024
WORD_EXTENSIONS = {".doc", ".docx"}
EXCEL_EXTENSIONS = {".xls", ".xlsx"}
PPT_EXTENSIONS = {".ppt", ".pptx"}
OFFICE_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS | PPT_EXTENSIONS
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".amr"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".wmv", ".mkv", ".webm", ".flv"}


def _parse_auxiliary_file_notes(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return []
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item or "").strip() for item in data]


def _parse_auxiliary_file_meta(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return []
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if isinstance(item, dict):
            rows.append(
                {
                    "name": str(item.get("name") or "").strip(),
                    "note": str(item.get("note") or "").strip(),
                }
            )
            continue
        rows.append({"name": "", "note": str(item or "").strip()})
    return rows


def _validate_auxiliary_files(files):
    for upload in files or []:
        if not upload or not getattr(upload, "name", ""):
            continue
        if upload.size > MAX_AUXILIARY_FILE_SIZE:
            return f"附件“{upload.name}”超过 5MB，请压缩后再上传。"
    return ""


def _attachment_preview_kind(attachment):
    name = (attachment.original_name or attachment.file.name or "").lower()
    ext = os.path.splitext(name)[1]
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in WORD_EXTENSIONS:
        return "word"
    return "other"


def _extract_docx_text(attachment_file, max_chars=12000):
    try:
        with zipfile.ZipFile(attachment_file.open("rb")) as docx_zip:
            with docx_zip.open("word/document.xml") as document_xml:
                xml_bytes = document_xml.read()
    except Exception:
        return ""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines = []
    for paragraph in root.findall(".//w:p", ns):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        line = "".join(texts).strip()
        if line:
            lines.append(line)
    content = "\n".join(lines)
    if len(content) > max_chars:
        return f"{content[:max_chars]}..."
    return content


def _save_auxiliary_attachments(*, treatment=None, followup=None, files=None, file_meta=None, uploaded_by=None):
    owner_field = "treatment" if treatment is not None else "followup"
    owner = treatment if treatment is not None else followup
    if owner is None:
        return
    normalized_meta = file_meta or []
    for index, upload in enumerate(files or []):
        if not upload or not getattr(upload, "name", ""):
            continue
        meta = normalized_meta[index] if index < len(normalized_meta) else {}
        custom_name = str((meta or {}).get("name") or "").strip()
        note = str((meta or {}).get("note") or "").strip()
        upload_ext = os.path.splitext(os.path.basename(upload.name))[1]
        if custom_name:
            custom_ext = os.path.splitext(custom_name)[1]
            final_name = custom_name if custom_ext else f"{custom_name}{upload_ext}"
        elif note:
            note_ext = os.path.splitext(note)[1]
            final_name = note if note_ext else f"{note}{upload_ext}"
        else:
            final_name = upload.name
        AuxiliaryExamAttachment.objects.create(
            **{owner_field: owner},
            file=upload,
            original_name=os.path.basename(final_name),
            note=note,
            uploaded_by=uploaded_by,
        )


def _ordered_treatments(patient):
    return sorted(
        patient.treatments.all(),
        key=lambda item: (item.start_date or date.min, item.created_at),
    )


def _build_detail_export_tables(rows, include_project_enrollment=False, visible_project_ids=None):
    basic_rows = []
    treatment_rows = []
    followup_rows = []
    project_enrollment_rows = []
    scale_treatment_files = {}
    scale_followup_files = {}
    attachment_rows = []
    attachment_files = {}
    visible_project_id_set = set(visible_project_ids) if visible_project_ids is not None else None

    def _safe_name(text):
        value = re.sub(r'[\\/:*?"<>|]+', "_", (text or "").strip())
        return value or "未命名"

    def _store_attachment_file(zip_path, attachment):
        candidate = zip_path
        stem, ext = os.path.splitext(zip_path)
        suffix = 1
        while candidate in attachment_files:
            candidate = f"{stem}_{suffix}{ext}"
            suffix += 1
        with attachment.file.open("rb") as source:
            attachment_files[candidate] = source.read()
        return candidate

    def _ensure_template_definition(mapping, template_name):
        return mapping.setdefault(
            template_name,
            {
                "question_keys": [],
                "question_labels": {},
            },
        )

    def _collect_answer_map(answers_json):
        answer_map = {}
        for answer in (answers_json or []):
            if not isinstance(answer, dict):
                continue
            raw_key = str(answer.get("key") or "").strip()
            raw_label = str(answer.get("label") or "").strip()
            value = answer.get("value", answer.get("score"))
            normalized_value = value if value not in (None, "") else ""
            if raw_key:
                answer_map[raw_key] = normalized_value
            if raw_label:
                answer_map[raw_label] = normalized_value
        return answer_map

    template_definitions = {}
    for template in ScaleTemplate.objects.prefetch_related("items").order_by("name", "id"):
        definition = _ensure_template_definition(template_definitions, template.name)
        for item in template.items.all():
            if item.field_type == "group":
                continue
            key = (item.item_key or item.label or "").strip()
            if not key:
                continue
            if key not in definition["question_keys"]:
                definition["question_keys"].append(key)
            definition["question_labels"][key] = (item.label or key).strip()

    patients = (
        Patient.objects.filter(pk__in=[row["patient"].pk for row in rows])
        .prefetch_related(
            "project_enrollments__project",
            "project_enrollments__marker_by",
            "treatments__created_by",
            "treatments__updated_by",
            "treatments__auxiliary_attachments__uploaded_by",
            "treatments__scale_records__template",
            "treatments__scale_records__created_by",
            "treatments__scale_records__updated_by",
            "treatments__followups__created_by",
            "treatments__followups__updated_by",
            "treatments__followups__auxiliary_attachments__uploaded_by",
            "treatments__followups__scale_records__template",
            "treatments__followups__scale_records__created_by",
            "treatments__followups__scale_records__updated_by",
            "treatments__followups",
        )
        .order_by("patient_id", "created_at")
    )

    for patient in patients:
        outpatient_number = patient.outpatient_number or ""
        basic_rows.append(
            [
                outpatient_number,
                patient.name,
                patient.get_gender_display(),
                patient.birth_date or "",
                patient.current_age or "",
                patient.ethnicity,
                patient.phone,
                patient.address,
            ]
        )
        for enrollment in patient.project_enrollments.all():
            if (
                visible_project_id_set is not None
                and enrollment.project_id not in visible_project_id_set
            ):
                continue
            project_enrollment_rows.append(
                [
                    outpatient_number,
                    patient.name,
                    enrollment.project.name,
                    enrollment.group_name or "",
                    enrollment.enrollment_date or "",
                    _project_marker_label(enrollment.marker_status),
                    enrollment.marker_date or "",
                    enrollment.marker_note or "",
                    _display_user_name(enrollment.marker_by),
                    _display_datetime(enrollment.marker_updated_at),
                ]
            )

        treatments = _ordered_treatments(patient)
        total_treatments = len(treatments)
        for treatment_index, treatment in enumerate(treatments, start=1):
            treatment_label = f"第{treatment_index:02d}次诊疗"
            treatment_rows.append(
                [
                    outpatient_number,
                    patient.name,
                    treatment_label,
                    total_treatments,
                    treatment.treatment_name,
                    treatment.display_visit_unit,
                    treatment.start_date or "",
                    treatment.admission_date or "",
                    treatment.discharge_date or "",
                    treatment.total_weeks,
                    treatment.followup_interval_days,
                    treatment.status_label,
                    treatment.followup_closed_at or "",
                    treatment.completed_followup_count,
                    treatment.planned_followup_count,
                    treatment.next_followup_date or "",
                    treatment.chief_complaint,
                    treatment.present_illness,
                    treatment.past_history,
                    treatment.personal_history,
                    treatment.marital_history,
                    treatment.allergy_history,
                    treatment.family_history,
                    treatment.tongue_diagnosis,
                    treatment.pulse_diagnosis,
                    treatment.tcm_disease,
                    treatment.display_western_disease,
                    treatment.treatment_principle,
                    treatment.pathogenesis,
                    treatment.symptom_syndrome,
                    treatment.prescription,
                    treatment.prescription_usage_method,
                    treatment.auxiliary_exam_results,
                    treatment.notes,
                    _display_user_name(treatment.created_by),
                    _display_datetime(treatment.created_at),
                ]
            )
            for attachment in treatment.auxiliary_attachments.all():
                if not attachment.file:
                    continue
                file_name = _safe_name(attachment.original_name or os.path.basename(attachment.file.name))
                zip_path = f"附件/{patient.patient_id}_{_safe_name(patient.name)}/{treatment_label}/{file_name}"
                stored_path = _store_attachment_file(zip_path, attachment)
                attachment_rows.append(
                    [
                        outpatient_number,
                        patient.name,
                        treatment_label,
                        "",
                        attachment.original_name or os.path.basename(attachment.file.name),
                        attachment.note or "",
                        _display_user_name(attachment.uploaded_by),
                        _display_datetime(attachment.created_at),
                        stored_path,
                    ]
                )
            for record in treatment.scale_records.all():
                template_name = record.template.name
                definition = _ensure_template_definition(template_definitions, template_name)
                scale_bucket = scale_treatment_files.setdefault(template_name, {"rows": []})
                for answer in (record.answers_json or []):
                    if not isinstance(answer, dict):
                        continue
                    key = (answer.get("key") or answer.get("label") or "").strip()
                    if not key:
                        continue
                    if key not in definition["question_keys"]:
                        definition["question_keys"].append(key)
                    definition["question_labels"][key] = (
                        answer.get("label") or answer.get("key") or key
                    )
                answer_map = _collect_answer_map(record.answers_json)
                scale_bucket["rows"].append(
                    {
                        "patient_id": outpatient_number,
                        "patient_name": patient.name,
                        "treatment_label": treatment_label,
                        "total_treatments": total_treatments,
                        "record_notes": record.notes or "",
                        "created_by": _display_user_name(record.created_by),
                        "created_at": _display_datetime(record.created_at),
                        "answers": answer_map,
                    }
                )

            followups = list(treatment.followups.all())
            total_followups = len(followups)
            for followup in followups:
                followup_label = f"第{followup.visit_number:02d}次随访"
                followup_rows.append(
                    [
                        outpatient_number,
                        patient.name,
                        treatment_label,
                        total_treatments,
                        followup_label,
                        total_followups,
                        treatment.treatment_name,
                        followup.followup_date or "",
                        followup.planned_next_followup_date or "",
                        followup.symptoms,
                        followup.medication_adherence,
                        followup.adverse_events,
                        followup.auxiliary_exam_results,
                        followup.notes,
                        _display_user_name(followup.created_by),
                        _display_datetime(followup.created_at),
                    ]
                )
                for attachment in followup.auxiliary_attachments.all():
                    if not attachment.file:
                        continue
                    file_name = _safe_name(attachment.original_name or os.path.basename(attachment.file.name))
                    zip_path = (
                        f"附件/{patient.patient_id}_{_safe_name(patient.name)}/{treatment_label}/"
                        f"{followup_label}/{file_name}"
                    )
                    stored_path = _store_attachment_file(zip_path, attachment)
                    attachment_rows.append(
                        [
                            outpatient_number,
                            patient.name,
                            treatment_label,
                            followup_label,
                            attachment.original_name or os.path.basename(attachment.file.name),
                            attachment.note or "",
                            _display_user_name(attachment.uploaded_by),
                            _display_datetime(attachment.created_at),
                            stored_path,
                        ]
                    )
                for record in followup.scale_records.all():
                    template_name = record.template.name
                    definition = _ensure_template_definition(template_definitions, template_name)
                    scale_bucket = scale_followup_files.setdefault(template_name, {"rows": []})
                    for answer in (record.answers_json or []):
                        if not isinstance(answer, dict):
                            continue
                        key = (answer.get("key") or answer.get("label") or "").strip()
                        if not key:
                            continue
                        if key not in definition["question_keys"]:
                            definition["question_keys"].append(key)
                        definition["question_labels"][key] = (
                            answer.get("label") or answer.get("key") or key
                        )
                    answer_map = _collect_answer_map(record.answers_json)
                    scale_bucket["rows"].append(
                        {
                            "patient_id": outpatient_number,
                            "patient_name": patient.name,
                            "treatment_label": treatment_label,
                            "total_treatments": total_treatments,
                            "followup_label": followup_label,
                            "total_followups": total_followups,
                            "record_notes": record.notes or "",
                            "created_by": _display_user_name(record.created_by),
                            "created_at": _display_datetime(record.created_at),
                            "answers": answer_map,
                        }
                    )

    tables = {
        "基本信息.csv": _csv_bytes(
            ["门诊号", "姓名", "性别", "出生日期", "当前年龄", "民族", "电话", "住址"],
            basic_rows,
        ),
        "诊疗记录.csv": _csv_bytes(
            [
                "门诊号",
                "姓名",
                "诊疗序号",
                "诊疗总次数",
                "治疗方案",
                "就诊单位",
                "治疗开始日期",
                "入院日期",
                "出院日期",
                "总随访周数",
                "随访间隔（天）",
                "当前状态",
                "结束回访日期",
                "已完成随访",
                "计划随访",
                "下次随访日期",
                "主诉",
                "现病史",
                "既往史",
                "个人史",
                "婚育史",
                "过敏史",
                "家族史",
                "舌诊",
                "脉诊",
                "中医疾病",
                "西医疾病",
                "治则治法",
                "病因病机",
                "症状/证候",
                "处方",
                "用药方式",
                "辅助检查",
                "备注",
                "录入人",
                "录入时间",
            ],
            treatment_rows,
        ),
        "随访记录.csv": _csv_bytes(
            [
                "门诊号",
                "姓名",
                "诊疗序号",
                "诊疗总次数",
                "随访序号",
                "该诊疗下随访总次数",
                "治疗方案",
                "随访日期",
                "下次建议随访日期",
                "症状变化",
                "用药依从性",
                "不良反应",
                "辅助检查",
                "备注",
                "录入人",
                "录入时间",
            ],
            followup_rows,
        ),
    }
    if include_project_enrollment:
        tables["项目入组信息.csv"] = _csv_bytes(
            [
                "门诊号",
                "姓名",
                "项目名称",
                "项目分组",
                "入组日期",
                "标记状态",
                "标记日期",
                "标记说明",
                "标记人",
                "标记更新时间",
            ],
            project_enrollment_rows,
        )
    all_template_names = sorted(
        set(scale_treatment_files.keys())
        | set(scale_followup_files.keys())
    )
    for template_name in all_template_names:
        definition = _ensure_template_definition(template_definitions, template_name)
        question_keys = definition["question_keys"]
        question_labels = definition["question_labels"]
        payload = scale_treatment_files.get(template_name, {"rows": []})
        if not payload["rows"]:
            continue
        values = []
        for row in payload["rows"]:
            value_columns = [row["answers"].get(key, "") for key in question_keys]
            values.append(
                [
                    template_name,
                    row["patient_id"],
                    row["patient_name"],
                    row["treatment_label"],
                    row["total_treatments"],
                    *value_columns,
                    row["record_notes"],
                    row["created_by"],
                    row["created_at"],
                ]
            )
        tables[f"量表_诊疗汇总_{_safe_name(template_name)}.csv"] = _csv_bytes(
            [
                "量表名称",
                "门诊号",
                "患者姓名",
                "诊疗序号",
                "诊疗总次数",
                *[question_labels[key] for key in question_keys],
                "量表备注",
                "记录人",
                "记录时间",
            ],
            values,
        )
    for template_name in all_template_names:
        definition = _ensure_template_definition(template_definitions, template_name)
        question_keys = definition["question_keys"]
        question_labels = definition["question_labels"]
        payload = scale_followup_files.get(template_name, {"rows": []})
        if not payload["rows"]:
            continue
        values = []
        for row in payload["rows"]:
            value_columns = [row["answers"].get(key, "") for key in question_keys]
            values.append(
                [
                    template_name,
                    row["patient_id"],
                    row["patient_name"],
                    row["treatment_label"],
                    row["total_treatments"],
                    row["followup_label"],
                    row["total_followups"],
                    *value_columns,
                    row["record_notes"],
                    row["created_by"],
                    row["created_at"],
                ]
            )
        tables[f"量表_随访汇总_{_safe_name(template_name)}.csv"] = _csv_bytes(
            [
                "量表名称",
                "门诊号",
                "患者姓名",
                "诊疗序号",
                "诊疗总次数",
                "随访序号",
                "该诊疗下随访总次数",
                *[question_labels[key] for key in question_keys],
                "量表备注",
                "记录人",
                "记录时间",
            ],
            values,
        )
    tables["附件清单.csv"] = _csv_bytes(
        [
            "门诊号",
            "患者姓名",
            "诊疗序号",
            "随访序号",
            "附件名称",
            "附件备注",
            "上传人",
            "上传时间",
            "压缩包内路径",
        ],
        attachment_rows,
    )
    tables.update(attachment_files)
    return tables


@login_required
def patient_list(request):
    visible_project_ids = _get_visible_project_ids_for_user(request.user)
    filter_form, rows, cleaned, all_rows, data_signature = _get_filtered_rows(
        request.GET,
        visible_project_ids=visible_project_ids,
    )
    for row in rows:
        row["can_edit"] = can_modify_record(request.user, row["patient"])
    stats = _get_cached_dashboard_stats(all_rows, data_signature)
    view_mode = cleaned.get("view") or "card"
    paginator = Paginator(rows, 6 if view_mode == "card" else 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    ordering = request.GET.get("ordering") or "next_followup_date"

    def next_order(field_name):
        return f"-{field_name}" if ordering == field_name else field_name

    return render(
        request,
        "followup/patient_list.html",
        {
            "app_name": settings.APP_NAME,
            "filter_form": filter_form,
            "page_obj": page_obj,
            "view_mode": view_mode,
            "stats": stats,
            "current_query": request.GET.urlencode(),
            "toggle_card_query": _encode_query(request, view="card", page=None),
            "toggle_table_query": _encode_query(request, view="table", page=None),
            "prev_page_query": _encode_query(
                request,
                page=page_obj.previous_page_number() if page_obj.has_previous() else None,
            ),
            "next_page_query": _encode_query(
                request,
                page=page_obj.next_page_number() if page_obj.has_next() else None,
            ),
            "sort_queries": {
                "patient_id": _encode_query(request, ordering=next_order("patient_id"), page=None),
                "name": _encode_query(request, ordering=next_order("name"), page=None),
                "age": _encode_query(request, ordering=next_order("age"), page=None),
                "ethnicity": _encode_query(request, ordering=next_order("ethnicity"), page=None),
                "tcm_disease": _encode_query(request, ordering=next_order("tcm_disease"), page=None),
                "western_disease": _encode_query(
                    request, ordering=next_order("western_disease"), page=None
                ),
                "treatment_count": _encode_query(
                    request, ordering=next_order("treatment_count"), page=None
                ),
                "followup_count": _encode_query(
                    request, ordering=next_order("followup_count"), page=None
                ),
                "start_date": _encode_query(request, ordering=next_order("start_date"), page=None),
                "next_followup_date": _encode_query(
                    request, ordering=next_order("next_followup_date"), page=None
                ),
                "status": _encode_query(request, ordering=next_order("status"), page=None),
            },
        },
    )


@login_required
def patient_create(request):
    if request.method == "POST":
        patient_form = PatientForm(request.POST)
        if patient_form.is_valid():
            patient = patient_form.save(commit=False)
            patient.created_by = request.user
            patient.save()
            messages.success(request, "患者已创建。")
            return redirect("patient_detail", pk=patient.pk)
    else:
        patient_form = PatientForm()
    return render(
        request,
        "followup/patient_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "新建患者",
            "submit_label": "保存",
            "patient_form": patient_form,
        },
    )


@login_required
def patient_update(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    denied = _ensure_modify_permission(request, patient, "patient_detail", patient.pk)
    if denied:
        return denied
    if request.method == "POST":
        patient_form = PatientForm(request.POST, instance=patient)
        if patient_form.is_valid():
            patient = patient_form.save(commit=False)
            patient.updated_by = request.user
            patient.updated_at = timezone.now()
            patient.save()
            messages.success(request, "患者主档案已更新。")
            return redirect("patient_detail", pk=patient.pk)
    else:
        patient_form = PatientForm(instance=patient)
    return render(
        request,
        "followup/patient_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "编辑患者",
            "submit_label": "更新",
            "patient_form": patient_form,
            "patient": patient,
        },
    )


@login_required
def patient_delete(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    denied = _ensure_modify_permission(request, patient, "patient_detail", patient.pk)
    if denied:
        return denied
    if request.method == "POST":
        patient.delete()
        messages.success(request, "患者及其相关诊疗、随访记录已删除。")
        return redirect("patient_list")
    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除患者",
            "description": f"将删除患者“{patient.name}”及其全部诊疗和随访记录，此操作不可恢复。",
            "cancel_url": reverse("patient_detail", args=[patient.pk]),
        },
    )


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(
        Patient.objects.prefetch_related(
            "treatments__created_by",
            "treatments__updated_by",
            "treatments__followups",
            "treatments__auxiliary_attachments__uploaded_by",
            "treatments__followups__auxiliary_attachments__uploaded_by",
            "treatments__prescription_items",
            "treatments__scale_records__template",
            "treatments__scale_records__template__items",
            "treatments__followups__scale_records__template",
            "treatments__followups__scale_records__template__items",
        ).select_related("created_by", "updated_by"),
        pk=pk,
    )
    ordered_treatments = _ordered_treatments(patient)
    latest_pk = ordered_treatments[-1].pk if ordered_treatments else None
    active_terms = ClinicalTerm.objects.filter(is_active=True).values_list("category", "name")
    known_term_map = {}
    for category, name in active_terms:
        known_term_map.setdefault(category, set()).add((name or "").strip().lower())
    known_herb_names = known_term_map.get(ClinicalTerm.CATEGORY_HERB, set())
    known_tcm_disease_names = known_term_map.get(ClinicalTerm.CATEGORY_TCM_DISEASE, set())
    known_western_disease_names = known_term_map.get(ClinicalTerm.CATEGORY_WESTERN_DISEASE, set())
    known_treatment_principle_names = known_term_map.get(ClinicalTerm.CATEGORY_TREATMENT_PRINCIPLE, set())
    known_pathogenesis_names = known_term_map.get(ClinicalTerm.CATEGORY_PATHOGENESIS, set())
    known_symptom_names = known_term_map.get(ClinicalTerm.CATEGORY_SYMPTOM, set())
    scale_record_detail_map = {}
    treatment_rows = []
    for sequence, treatment in enumerate(ordered_treatments, start=1):
        prescription_items = list(treatment.prescription_items.all())
        prescription_view_items = []
        for index, item in enumerate(prescription_items, start=1):
            herb_name = (item.herb_name or "").strip()
            prescription_view_items.append(
                {
                    "index": index,
                    "herb_name": herb_name,
                    "known_herb": herb_name.lower() in known_herb_names if herb_name else False,
                    "dosage": item.dosage,
                    "unit": item.unit,
                    "usage": item.usage,
                    "dosage_missing": not (item.dosage or "").strip(),
                    "unit_missing": not (item.unit or "").strip(),
                }
            )
        followup_rows = [
            {
                "object": item,
                "can_modify": can_modify_record(request.user, item),
                "scale_records": _serialize_scale_record_list(item.scale_records.all()),
                "auxiliary_attachments": list(item.auxiliary_attachments.all()),
            }
            for item in treatment.followups.all()
        ]
        treatment_rows.append(
            {
                "treatment": treatment,
                "prescription_items": prescription_items,
                "prescription_view_items": prescription_view_items,
                "tcm_disease_tags": _build_known_tag_items(treatment.tcm_disease, known_tcm_disease_names),
                "western_disease_tags": _build_known_tag_items(
                    treatment.display_western_disease,
                    known_western_disease_names,
                ),
                "treatment_principle_tags": _build_known_tag_items(
                    treatment.treatment_principle, known_treatment_principle_names
                ),
                "pathogenesis_tags": _build_known_tag_items(treatment.pathogenesis, known_pathogenesis_names),
                "symptom_syndrome_tags": _build_known_tag_items(treatment.symptom_syndrome, known_symptom_names),
                "followups": followup_rows,
                "scale_records": _serialize_scale_record_list(treatment.scale_records.all()),
                "auxiliary_attachments": list(treatment.auxiliary_attachments.all()),
                "next_visit_number": treatment.next_followup_number,
                "sequence": sequence,
                "is_latest": treatment.pk == latest_pk,
                "can_modify": can_modify_record(request.user, treatment),
            }
        )
        for record in treatment.scale_records.all():
            progress = _scale_record_progress(record)
            scale_record_detail_map[str(record.pk)] = {
                "id": record.pk,
                "template_name": record.template.name,
                "template_description": record.template.description or "",
                "filled_count": progress["filled_count"],
                "total_count": progress["total_count"],
                "recorder_name": _display_user_name(record.created_by) or "-",
                "record_time": _display_datetime(record.created_at) or "-",
                "notes": record.notes or "",
                "sections": _build_scale_record_sections(record),
            }
        for followup in treatment.followups.all():
            for record in followup.scale_records.all():
                progress = _scale_record_progress(record)
                scale_record_detail_map[str(record.pk)] = {
                    "id": record.pk,
                    "template_name": record.template.name,
                    "template_description": record.template.description or "",
                    "filled_count": progress["filled_count"],
                    "total_count": progress["total_count"],
                    "recorder_name": _display_user_name(record.created_by) or "-",
                    "record_time": _display_datetime(record.created_at) or "-",
                    "notes": record.notes or "",
                    "sections": _build_scale_record_sections(record),
                }
    treatment_rows.reverse()
    return render(
        request,
        "followup/patient_detail.html",
        {
            "patient": patient,
            "treatment_rows": treatment_rows,
            "scale_record_detail_map": scale_record_detail_map,
            "can_modify_patient": can_modify_record(request.user, patient),
            "ai_options": {
                "include_basic": True,
                "include_latest_treatment": True,
                "include_recent_followups": True,
                "include_full_history": False,
            },
            "ai_model_choices": settings.AI_TEXT_MODEL_CHOICES,
            "ai_default_model": settings.AI_MODEL,
        },
    )


@login_required
def patient_ai_chat(request, pk):
    if request.method != "POST":
        return _json_error("仅支持 POST 请求。", status=405)

    patient = get_object_or_404(Patient, pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json_error("请求内容不是有效的 JSON。")
    if not isinstance(payload, dict):
        return _json_error("请求内容必须是 JSON 对象。")

    message = (payload.get("message") or "").strip()
    if not message:
        return _json_error("请输入问题后再发送。")

    options = {
        "include_basic": _coerce_bool(payload.get("include_basic"), default=True),
        "include_latest_treatment": _coerce_bool(payload.get("include_latest_treatment"), default=True),
        "include_recent_followups": _coerce_bool(payload.get("include_recent_followups"), default=True),
        "include_full_history": _coerce_bool(payload.get("include_full_history"), default=False),
    }
    allowed_models = set(settings.AI_TEXT_MODEL_CHOICES)
    model_name = str(payload.get("model") or "").strip() or settings.AI_MODEL
    if model_name not in allowed_models:
        return _json_error("所选模型不可用，请重新选择。", status=400)

    try:
        reply, context = chat_with_patient(
            patient,
            message,
            history=payload.get("history") or [],
            options=options,
            model_name=model_name,
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except AIServiceError as exc:
        return _json_error(str(exc), status=exc.status_code)
    except Exception:
        logger.exception("Patient AI chat failed", extra={"patient_pk": patient.pk})
        return _json_error("智随暂时不可用，请稍后重试。", status=502)

    return JsonResponse({"ok": True, "reply": reply, "context": context, "model": model_name})


@login_required
def treatment_create(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    if request.method == "POST":
        form = TreatmentForm(request.POST, request.FILES)
        auxiliary_files = request.FILES.getlist("auxiliary_exam_files")
        auxiliary_meta = _parse_auxiliary_file_meta(request.POST.get("auxiliary_exam_file_meta_json"))
        if not auxiliary_meta:
            auxiliary_notes = _parse_auxiliary_file_notes(request.POST.get("auxiliary_exam_file_notes_json"))
            auxiliary_meta = [{"name": "", "note": note} for note in auxiliary_notes]
        file_error = _validate_auxiliary_files(auxiliary_files)
        if file_error:
            messages.error(request, file_error)
        if form.is_valid() and not file_error:
            treatment = form.save(commit=False)
            treatment.patient = patient
            treatment.created_by = request.user
            treatment.save()
            form.save_prescription_items(treatment)
            form.save_scale_records(treatment, actor=request.user)
            _save_auxiliary_attachments(
                treatment=treatment,
                files=auxiliary_files,
                file_meta=auxiliary_meta,
                uploaded_by=request.user,
            )
            messages.success(request, "新的诊疗记录已创建。")
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = TreatmentForm()
    return render(
        request,
        "followup/treatment_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "新增诊疗",
            "submit_label": "保存诊疗",
            "patient": patient,
            "form": form,
        },
    )


@login_required
def treatment_update(request, pk):
    treatment = get_object_or_404(Treatment.objects.select_related("patient"), pk=pk)
    denied = _ensure_modify_permission(request, treatment, "patient_detail", treatment.patient.pk)
    if denied:
        return denied
    if request.method == "POST":
        form = TreatmentForm(request.POST, request.FILES, instance=treatment)
        auxiliary_files = request.FILES.getlist("auxiliary_exam_files")
        auxiliary_meta = _parse_auxiliary_file_meta(request.POST.get("auxiliary_exam_file_meta_json"))
        if not auxiliary_meta:
            auxiliary_notes = _parse_auxiliary_file_notes(request.POST.get("auxiliary_exam_file_notes_json"))
            auxiliary_meta = [{"name": "", "note": note} for note in auxiliary_notes]
        file_error = _validate_auxiliary_files(auxiliary_files)
        if file_error:
            messages.error(request, file_error)
        if form.is_valid() and not file_error:
            treatment = form.save(commit=False)
            treatment.updated_by = request.user
            treatment.updated_at = timezone.now()
            treatment.save()
            form.save_prescription_items(treatment)
            form.save_scale_records(treatment, actor=request.user)
            _save_auxiliary_attachments(
                treatment=treatment,
                files=auxiliary_files,
                file_meta=auxiliary_meta,
                uploaded_by=request.user,
            )
            messages.success(request, "诊疗记录已更新。")
            return redirect("patient_detail", pk=treatment.patient.pk)
    else:
        form = TreatmentForm(instance=treatment)
    return render(
        request,
        "followup/treatment_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "编辑诊疗",
            "submit_label": "更新诊疗",
            "patient": treatment.patient,
            "form": form,
        },
    )


@login_required
def treatment_delete(request, pk):
    treatment = get_object_or_404(Treatment.objects.select_related("patient"), pk=pk)
    denied = _ensure_modify_permission(request, treatment, "patient_detail", treatment.patient.pk)
    if denied:
        return denied
    if request.method == "POST":
        patient_pk = treatment.patient.pk
        treatment.delete()
        messages.success(request, "诊疗记录及其随访已删除。")
        return redirect("patient_detail", pk=patient_pk)
    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除诊疗",
            "description": f"将删除“{treatment.treatment_name}”及其全部随访记录，此操作不可恢复。",
            "cancel_url": reverse("patient_detail", args=[treatment.patient.pk]),
        },
    )


@login_required
def treatment_toggle_followup(request, pk):
    treatment = get_object_or_404(Treatment.objects.select_related("patient"), pk=pk)
    denied = _ensure_modify_permission(request, treatment, "patient_detail", treatment.patient.pk)
    if denied:
        return denied
    if request.method != "POST":
        return redirect("patient_detail", pk=treatment.patient.pk)

    if treatment.followup_closed:
        treatment.reopen_followup()
        messages.success(request, "该诊疗已重新启动回访。")
    else:
        treatment.close_followup()
        messages.success(request, "该诊疗已结束回访，后续计划随访将不再提醒。")
    return redirect("patient_detail", pk=treatment.patient.pk)


@login_required
def followup_create(request, treatment_id):
    treatment = get_object_or_404(Treatment, pk=treatment_id)
    initial = {"visit_number": treatment.next_followup_number}
    scheduled_next_followup_date = treatment.next_followup_date
    if request.method == "POST":
        form = FollowUpForm(request.POST, request.FILES, initial=initial, treatment=treatment)
        auxiliary_files = request.FILES.getlist("auxiliary_exam_files")
        auxiliary_meta = _parse_auxiliary_file_meta(request.POST.get("auxiliary_exam_file_meta_json"))
        if not auxiliary_meta:
            auxiliary_notes = _parse_auxiliary_file_notes(request.POST.get("auxiliary_exam_file_notes_json"))
            auxiliary_meta = [{"name": "", "note": note} for note in auxiliary_notes]
        file_error = _validate_auxiliary_files(auxiliary_files)
        if file_error:
            messages.error(request, file_error)
        if form.is_valid() and not file_error:
            followup = form.save(commit=False)
            followup.treatment = treatment
            followup.created_by = request.user
            followup.save()
            form.save_scale_records(followup, actor=request.user)
            _save_auxiliary_attachments(
                followup=followup,
                files=auxiliary_files,
                file_meta=auxiliary_meta,
                uploaded_by=request.user,
            )
            if treatment.followup_closed:
                treatment.reopen_followup()
            messages.success(request, "随访记录已保存。")
            return redirect("patient_detail", pk=treatment.patient.pk)
    else:
        form = FollowUpForm(initial=initial, treatment=treatment)
    return render(
        request,
        "followup/followup_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "录入随访",
            "submit_label": "保存随访",
            "form": form,
            "treatment": treatment,
            "followup_interval_days": treatment.followup_interval_days,
            "scheduled_next_followup_date": scheduled_next_followup_date,
        },
    )


@login_required
def followup_update(request, pk):
    followup = get_object_or_404(FollowUp.objects.select_related("treatment__patient"), pk=pk)
    denied = _ensure_modify_permission(
        request,
        followup,
        "patient_detail",
        followup.treatment.patient.pk,
    )
    if denied:
        return denied
    if request.method == "POST":
        form = FollowUpForm(request.POST, request.FILES, instance=followup, treatment=followup.treatment)
        auxiliary_files = request.FILES.getlist("auxiliary_exam_files")
        auxiliary_meta = _parse_auxiliary_file_meta(request.POST.get("auxiliary_exam_file_meta_json"))
        if not auxiliary_meta:
            auxiliary_notes = _parse_auxiliary_file_notes(request.POST.get("auxiliary_exam_file_notes_json"))
            auxiliary_meta = [{"name": "", "note": note} for note in auxiliary_notes]
        file_error = _validate_auxiliary_files(auxiliary_files)
        if file_error:
            messages.error(request, file_error)
        if form.is_valid() and not file_error:
            followup = form.save(commit=False)
            followup.updated_by = request.user
            followup.updated_at = timezone.now()
            followup.save()
            form.save_scale_records(followup, actor=request.user)
            _save_auxiliary_attachments(
                followup=followup,
                files=auxiliary_files,
                file_meta=auxiliary_meta,
                uploaded_by=request.user,
            )
            messages.success(request, "随访记录已更新。")
            return redirect("patient_detail", pk=followup.treatment.patient.pk)
    else:
        form = FollowUpForm(instance=followup, treatment=followup.treatment)
    return render(
        request,
        "followup/followup_form.html",
        {
            "app_name": settings.APP_NAME,
            "page_title": "编辑随访",
            "submit_label": "更新随访",
            "form": form,
            "treatment": followup.treatment,
            "followup_interval_days": followup.treatment.followup_interval_days,
            "scheduled_next_followup_date": followup.treatment.next_followup_date,
        },
    )


@login_required
def followup_delete(request, pk):
    followup = get_object_or_404(FollowUp.objects.select_related("treatment__patient"), pk=pk)
    denied = _ensure_modify_permission(
        request,
        followup,
        "patient_detail",
        followup.treatment.patient.pk,
    )
    if denied:
        return denied
    if request.method == "POST":
        patient_pk = followup.treatment.patient.pk
        followup.delete()
        messages.success(request, "随访记录已删除。")
        return redirect("patient_detail", pk=patient_pk)
    return render(
        request,
        "followup/confirm_delete.html",
        {
            "app_name": settings.APP_NAME,
            "title": "删除随访",
            "description": f"将删除第 {followup.visit_number} 次随访记录，此操作不可恢复。",
            "cancel_url": reverse("patient_detail", args=[followup.treatment.patient.pk]),
        },
    )


@login_required
def auxiliary_attachment_download(request, pk):
    attachment = get_object_or_404(
        AuxiliaryExamAttachment.objects.select_related(
            "treatment__patient",
            "followup__treatment__patient",
        ),
        pk=pk,
    )
    if not attachment.file:
        return _json_error("附件不存在。", status=404)
    filename = attachment.original_name or os.path.basename(attachment.file.name)
    return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=filename)


@login_required
def auxiliary_attachment_preview(request, pk):
    attachment = get_object_or_404(
        AuxiliaryExamAttachment.objects.select_related(
            "treatment__patient",
            "followup__treatment__patient",
        ),
        pk=pk,
    )
    if not attachment.file:
        return _json_error("附件不存在。", status=404)
    file_name = attachment.original_name or os.path.basename(attachment.file.name)
    lower_name = file_name.lower()
    suffix = os.path.splitext(lower_name)[1]
    content_type, _ = mimetypes.guess_type(file_name)
    if suffix in AUDIO_EXTENSIONS or suffix in VIDEO_EXTENSIONS or (
        content_type and (content_type.startswith("audio/") or content_type.startswith("video/"))
    ):
        return render(
            request,
            "followup/attachment_preview.html",
            {
                "attachment": attachment,
                "file_name": file_name,
                "preview_kind": "blocked_media",
                "preview_text": "",
                "office_preview_url": "",
            },
        )

    if suffix in IMAGE_EXTENSIONS:
        response = FileResponse(attachment.file.open("rb"), as_attachment=False)
        response["Content-Type"] = content_type or "image/*"
        return response

    if suffix in PDF_EXTENSIONS:
        response = FileResponse(attachment.file.open("rb"), as_attachment=False)
        response["Content-Type"] = "application/pdf"
        return response

    if suffix in OFFICE_EXTENSIONS:
        if suffix == ".docx":
            preview_text = _extract_docx_text(attachment.file)
            return render(
                request,
                "followup/attachment_preview.html",
                {
                    "attachment": attachment,
                    "file_name": file_name,
                    "preview_kind": "docx",
                    "preview_text": preview_text,
                    "office_preview_url": "",
                },
            )
        source_url = request.build_absolute_uri(
            reverse("auxiliary_attachment_download", args=[attachment.pk])
        )
        office_preview_url = (
            "https://view.officeapps.live.com/op/embed.aspx?src="
            f"{quote(source_url, safe='')}"
        )
        return render(
            request,
            "followup/attachment_preview.html",
            {
                "attachment": attachment,
                "file_name": file_name,
                    "preview_kind": "office",
                    "office_preview_url": office_preview_url,
                },
            )

    if content_type and (content_type.startswith("text/") or content_type in {"application/json"}):
        try:
            with attachment.file.open("r", encoding="utf-8", errors="ignore") as source:
                preview_text = source.read(12000)
        except Exception:
            preview_text = ""
        return render(
            request,
            "followup/attachment_preview.html",
            {
                "attachment": attachment,
                "file_name": file_name,
                "preview_kind": "text",
                "preview_text": preview_text,
                "office_preview_url": "",
            },
        )

    return render(
        request,
        "followup/attachment_preview.html",
        {
            "attachment": attachment,
            "file_name": file_name,
            "preview_kind": "other",
            "office_preview_url": "",
        },
    )


@login_required
def auxiliary_attachment_delete(request, pk):
    attachment = get_object_or_404(
        AuxiliaryExamAttachment.objects.select_related(
            "treatment__patient",
            "followup__treatment__patient",
        ),
        pk=pk,
    )
    owner = attachment.followup or attachment.treatment
    if not owner:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "未找到附件所属记录。"}, status=400)
        messages.error(request, "未找到附件所属记录。")
        return redirect("patient_list")
    if not can_modify_record(request.user, owner):
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "当前账号无权删除该附件。"}, status=403)
        denied = _ensure_modify_permission(
            request,
            owner,
            "patient_detail",
            owner.treatment.patient.pk if hasattr(owner, "treatment") else owner.patient.pk,
        )
        if denied:
            return denied
    next_url = request.POST.get("next") or request.GET.get("next")
    if request.method == "POST":
        attachment.delete()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": True})
        messages.success(request, "附件已删除。")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        return redirect(next_url)
    if attachment.followup_id:
        return redirect("followup_update", pk=attachment.followup_id)
    return redirect("treatment_update", pk=attachment.treatment_id)


@login_required
def patient_export(request):
    denied = _ensure_export_permission(request)
    if denied:
        return denied
    rows = _get_export_rows(request)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="patients_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "门诊号",
            "姓名",
            "性别",
            "出生日期",
            "当前年龄",
            "民族",
            "电话",
            "住址",
            "最新就诊单位",
            "西医疾病",
            "治疗方案",
            "治疗开始日期",
            "入院日期",
            "出院日期",
            "当前状态",
            "已完成随访",
            "计划随访",
            "下次随访日期",
            "项目入组标记",
        ]
    )
    for row in rows:
        patient = row["patient"]
        treatment = row["treatment"]
        enrollment_text = "；".join(
            (
                f"{tag.get('project_name') or ''}"
                f"{(' · ' + (tag.get('group_name') or '')) if tag.get('group_name') else ''}"
                f" · {_project_marker_label(tag.get('marker_status') or '')}"
            )
            for tag in row.get("project_tags", [])
        )
        writer.writerow(
            [
                patient.outpatient_number or "",
                patient.name,
                patient.get_gender_display(),
                patient.birth_date or "",
                patient.current_age or "",
                patient.ethnicity,
                patient.phone,
                patient.address,
                row["visit_unit"],
                row["western_disease"],
                treatment.treatment_name if treatment else "",
                row["start_date"] or "",
                treatment.admission_date if treatment else "",
                treatment.discharge_date if treatment else "",
                row["status"],
                row["completed_count"],
                row["planned_count"],
                row["next_followup_date"] or "",
                enrollment_text,
            ]
        )
    return response


@login_required
def patient_export_detail(request):
    denied = _ensure_export_permission(request)
    if denied:
        return denied
    rows = _get_export_rows(request)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_name, content in _build_detail_export_tables(rows, include_project_enrollment=False).items():
            zip_file.writestr(file_name, content)

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="patients_detail_export.zip"'
    return response


@login_required
def project_export(request, pk):
    if not can_export_project_data(request.user):
        return _redirect_with_error(request, "普通账号不能导出项目数据。", "project_list")
    project = get_object_or_404(get_project_queryset_for_user(request.user, ResearchProject.objects.all()), pk=pk)
    visible_project_ids = _get_visible_project_ids_for_user(request.user)
    rows = _get_project_export_rows(request, project, visible_project_ids=visible_project_ids)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="project_{project.pk}_patients_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "门诊号",
            "姓名",
            "性别",
            "出生日期",
            "当前年龄",
            "民族",
            "电话",
            "住址",
            "最新就诊单位",
            "中医疾病",
            "西医疾病",
            "治疗方案",
            "治疗开始日期",
            "入院日期",
            "出院日期",
            "当前状态",
            "已完成随访",
            "计划随访",
            "下次随访日期",
            "所属项目/分组",
            "当前项目标记",
            "标记日期",
            "标记说明",
            "标记人",
            "标记更新时间",
        ]
    )
    for row in rows:
        patient = row["patient"]
        treatment = row["treatment"]
        project_tag_text = "；".join(
            f"{tag['project_name']}{(' · ' + tag['group_name']) if tag.get('group_name') else ''}"
            for tag in row.get("project_tags_view", [])
        )
        writer.writerow(
            [
                patient.outpatient_number or "",
                patient.name,
                patient.get_gender_display(),
                patient.birth_date or "",
                patient.current_age or "",
                patient.ethnicity,
                patient.phone,
                patient.address,
                row["visit_unit"],
                row["tcm_disease"],
                row["western_disease"],
                treatment.treatment_name if treatment else "",
                row["start_date"] or "",
                treatment.admission_date if treatment else "",
                treatment.discharge_date if treatment else "",
                row["status"],
                row["completed_count"],
                row["planned_count"],
                row["next_followup_date"] or "",
                project_tag_text,
                row.get("marker_status_label") or "",
                row.get("marker_date") or "",
                row.get("marker_note") or "",
                row.get("marker_by") or "",
                row.get("marker_updated_at") or "",
            ]
        )
    return response


@login_required
def project_export_detail(request, pk):
    if not can_export_project_data(request.user):
        return _redirect_with_error(request, "普通账号不能导出项目数据。", "project_list")
    project = get_object_or_404(get_project_queryset_for_user(request.user, ResearchProject.objects.all()), pk=pk)
    visible_project_ids = _get_visible_project_ids_for_user(request.user)
    rows = _get_project_export_rows(request, project, visible_project_ids=visible_project_ids)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_name, content in _build_detail_export_tables(
            rows,
            include_project_enrollment=True,
            visible_project_ids=visible_project_ids,
        ).items():
            zip_file.writestr(file_name, content)

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="project_{project.pk}_patients_detail_export.zip"'
    return response
    visible_project_id_set = set(visible_project_ids) if visible_project_ids is not None else None
