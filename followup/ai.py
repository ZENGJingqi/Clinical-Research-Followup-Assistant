import json
from datetime import date

import requests
from django.conf import settings
from django.utils import timezone

try:
    from zai import ZhipuAiClient
except ImportError:  # pragma: no cover - optional dependency
    ZhipuAiClient = None


SYSTEM_PROMPT = """
你是“智随”，服务于“临床科研智能随访助手”。

你的角色是临床科研随访辅助助手，不是最终诊断者。

你的主要工作流：
1. 先按时间线理解患者资料，区分基本信息、当前诊疗、既往诊疗、最近随访和历史随访。
2. 优先识别“变化”：
   - 症状是否改善、加重或波动
   - 用药依从性是否下降
   - 是否出现不良反应
   - 下次随访日期、今日应随访、近期应随访或逾期风险
3. 再输出面向科研随访的辅助结论：
   - 当前状态摘要
   - 需要重点关注的风险点
   - 下一次随访建议重点
   - 资料缺口或建议补记内容
4. 如果用户要求生成记录、总结或条目，请直接按指定格式输出，语言适合写入诊疗/随访记录。

回答规则：
- 默认使用简体中文，表达直接、短句优先，便于临床科研记录。
- 只能基于已提供资料回答；资料不足时明确写出“不足以判断”或“资料未提供”。
- 不得编造化验结果、影像、诊断结论、治疗史或随访结果。
- 不替代医生作最终诊断，不给出确定性医疗结论。
- 如果提到风险、判断或建议，要尽量点明依据来自哪类资料或哪次随访变化。
- 如果用户问题偏行政或数据整理，就少做医学发挥，直接完成提取、归纳、对比或生成。
- 不要使用 Markdown 标题、代码块、表格或 `###` 这类标记。
- 回复要清晰，但不要被固定模板束缚。
- 如果内容简单，直接用一到两段或简短列表回答即可。
- 如果内容较复杂，可以自行分成若干小段或小标题，但只在确有必要时再分段。
""".strip()


class AIServiceError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def _safe_text(value):
    return value if value not in (None, "") else None


def _scale_record_payload(record):
    answers = []
    for item in record.answers_json or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value", item.get("score"))
        note = item.get("note")
        if value in (None, "") and not note:
            continue
        answers.append(
            {
                "label": item.get("label") or item.get("key"),
                "value": value,
                "note": _safe_text(note),
            }
        )
    return {
        "template": record.template.name,
        "recorded_at": record.created_at.isoformat() if record.created_at else None,
        "notes": _safe_text(record.notes),
        "answers": answers,
    }


def _prescription_item_payload(item):
    return {
        "herb_name": _safe_text(item.herb_name),
        "dosage": _safe_text(item.dosage),
        "unit": _safe_text(item.unit),
        "usage": _safe_text(item.usage),
        "display_text": _safe_text(item.display_text),
    }


def _followup_payload(followup):
    return {
        "visit_number": followup.visit_number,
        "followup_type": _safe_text(followup.get_followup_type_display()),
        "followup_date": str(followup.followup_date) if followup.followup_date else None,
        "planned_next_followup_date": (
            str(followup.planned_next_followup_date)
            if followup.planned_next_followup_date
            else None
        ),
        "symptoms": _safe_text(followup.symptoms),
        "medication_adherence": _safe_text(followup.medication_adherence),
        "adverse_events": _safe_text(followup.adverse_events),
        "chief_complaint": _safe_text(followup.chief_complaint),
        "present_illness": _safe_text(followup.present_illness),
        "tongue_diagnosis": _safe_text(followup.tongue_diagnosis),
        "pulse_diagnosis": _safe_text(followup.pulse_diagnosis),
        "treatment_principle": _safe_text(followup.treatment_principle),
        "prescription_summary": _safe_text(followup.prescription_summary),
        "auxiliary_exam_results": _safe_text(followup.auxiliary_exam_results),
        "notes": _safe_text(followup.notes),
        "scales": [_scale_record_payload(item) for item in followup.scale_records.select_related("template").all()],
    }


def _treatment_payload(treatment, include_followups=False, followup_limit=None):
    payload = {
        "treatment_name": treatment.treatment_name,
        "visit_unit": _safe_text(treatment.group_name),
        "start_date": str(treatment.start_date) if treatment.start_date else None,
        "admission_date": str(treatment.admission_date) if treatment.admission_date else None,
        "discharge_date": str(treatment.discharge_date) if treatment.discharge_date else None,
        "status": treatment.status_label,
        "total_weeks": treatment.total_weeks,
        "followup_interval_days": treatment.followup_interval_days,
        "completed_followup_count": treatment.completed_followup_count,
        "planned_followup_count": treatment.planned_followup_count,
        "next_followup_date": (
            str(treatment.next_followup_date) if treatment.next_followup_date else None
        ),
        "followup_closed_at": (
            str(treatment.followup_closed_at) if treatment.followup_closed_at else None
        ),
        "tcm_disease": _safe_text(treatment.tcm_disease),
        "western_disease": _safe_text(treatment.display_western_disease),
        "chief_complaint": _safe_text(treatment.chief_complaint),
        "present_illness": _safe_text(treatment.present_illness),
        "past_history": _safe_text(treatment.past_history),
        "personal_history": _safe_text(treatment.personal_history),
        "marital_history": _safe_text(treatment.marital_history),
        "allergy_history": _safe_text(treatment.allergy_history),
        "family_history": _safe_text(treatment.family_history),
        "tongue_diagnosis": _safe_text(treatment.tongue_diagnosis),
        "pulse_diagnosis": _safe_text(treatment.pulse_diagnosis),
        "treatment_principle": _safe_text(treatment.treatment_principle),
        "pathogenesis": _safe_text(treatment.pathogenesis),
        "symptom_syndrome": _safe_text(treatment.symptom_syndrome),
        "prescription": _safe_text(treatment.prescription),
        "prescription_usage_method": _safe_text(treatment.prescription_usage_method),
        "auxiliary_exam_results": _safe_text(treatment.auxiliary_exam_results),
        "notes": _safe_text(treatment.notes),
        "prescription_items": [
            _prescription_item_payload(item) for item in treatment.prescription_items.all().order_by("sort_order", "id")
        ],
        "scales": [_scale_record_payload(item) for item in treatment.scale_records.select_related("template").all()],
    }
    if include_followups:
        followups = list(treatment.followups.all().order_by("-visit_number", "-followup_date"))
        if followup_limit is not None:
            followups = followups[:followup_limit]
        payload["followups"] = [_followup_payload(item) for item in reversed(followups)]
    return payload


def build_patient_context(patient, options=None):
    options = options or {}
    include_basic = options.get("include_basic", True)
    include_latest_treatment = options.get("include_latest_treatment", True)
    include_recent_followups = options.get("include_recent_followups", True)
    include_full_history = options.get("include_full_history", False)

    context = {
        "app_name": settings.APP_NAME,
        "privacy_notice": "默认未发送患者姓名、电话、住址等直接身份识别信息。",
        "patient_id": patient.patient_id,
        "attachments_included": False,
    }

    if include_basic:
        context["basic_info"] = {
            "gender": patient.get_gender_display(),
            "current_age": patient.current_age,
            "birth_date": str(patient.birth_date) if patient.birth_date else None,
            "ethnicity": _safe_text(patient.ethnicity),
        }

    treatments_queryset = patient.treatments.prefetch_related(
        "prescription_items",
        "scale_records__template",
        "followups__scale_records__template",
    )

    ordered_treatments = []
    latest_treatment = None
    if include_full_history:
        treatments = list(treatments_queryset.all())
        if treatments:
            ordered_treatments = sorted(
                treatments,
                key=lambda item: (item.start_date or date.min, item.created_at),
            )
            latest_treatment = ordered_treatments[-1]
    else:
        latest_treatment = treatments_queryset.order_by("-start_date", "-created_at").first()

    if latest_treatment:
        if include_latest_treatment:
            context["latest_treatment"] = _treatment_payload(latest_treatment, include_followups=False)

        if include_recent_followups:
            recent_followups = list(
                latest_treatment.followups.order_by("-visit_number", "-followup_date")[:3]
            )
            context["recent_followups"] = [
                _followup_payload(item) for item in reversed(recent_followups)
            ]

    if include_full_history and ordered_treatments:
        context["treatment_history"] = [
            {
                "sequence": index,
                **_treatment_payload(treatment, include_followups=True),
            }
            for index, treatment in enumerate(ordered_treatments, start=1)
        ]

    return context


def _normalize_history(history):
    if not isinstance(history, list):
        return []
    normalized = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized[-8:]


def _extract_content(message_content):
    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        texts = []
        for item in message_content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    texts.append(text)
        if texts:
            return "\n".join(texts)
    return str(message_content)


def _extract_error_payload(response):
    try:
        error = response.json().get("error") or {}
    except ValueError:
        return {}
    return error if isinstance(error, dict) else {}


def _build_provider_payload(messages, model_name=None):
    payload = {
        "model": model_name or settings.AI_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000,
    }
    if settings.AI_PROVIDER == "zhipu":
        payload["thinking"] = {"type": "enabled"}
    return payload


def _chat_via_http(api_key, payload):
    session = requests.Session()
    session.trust_env = settings.AI_USE_ENV_PROXY
    try:
        response = session.post(
            settings.AI_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        error = _extract_error_payload(exc.response) if exc.response is not None else {}
        error_code = str(error.get("code") or "")
        error_message = str(error.get("message") or "").strip()
        if status_code in {401, 403}:
            raise AIServiceError("智随鉴权失败，请检查 API Key 配置。", 502) from exc
        if status_code == 429:
            if error_code == "1113" or "余额不足" in error_message:
                raise AIServiceError("智随余额不足或无可用资源包，请充值后再试。", 402) from exc
            raise AIServiceError("智随当前限流，请稍后再试。", 429) from exc
        if status_code >= 500:
            raise AIServiceError("智随模型服务暂时不可用，请稍后再试。", 502) from exc
        raise AIServiceError("智随请求失败，请稍后重试。", status_code) from exc
    except requests.RequestException as exc:
        raise AIServiceError("智随连接失败，请检查网络或代理配置。", 502) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise AIServiceError("智随返回内容解析失败，请稍后重试。", 502) from exc
    try:
        return _extract_content(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover - defensive
        raise AIServiceError("智随返回格式异常，请稍后重试。", 502) from exc


def chat_with_patient(patient, user_message, history=None, options=None, model_name=None):
    api_key = settings.AI_API_KEY
    if not api_key:
        raise ValueError("未配置 AI_API_KEY，暂时无法使用智随。")

    context = build_patient_context(patient, options=options)
    today_text = timezone.localdate().isoformat()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"当前系统日期：{today_text}。如需判断今日回访、近期随访或逾期，请以该日期为准。",
        },
        {
            "role": "system",
            "content": "当前患者上下文（仅用于本次详情页临时会话）:\n"
            + json.dumps(context, ensure_ascii=False),
        },
        *_normalize_history(history),
        {"role": "user", "content": user_message.strip()},
    ]
    payload = _build_provider_payload(messages, model_name=model_name)

    if settings.AI_PROVIDER == "zhipu" and ZhipuAiClient is not None:
        try:
            client = ZhipuAiClient(api_key=api_key)
            response = client.chat.completions.create(**payload)
        except Exception as exc:  # pragma: no cover - SDK optional
            raise AIServiceError("智随模型服务调用失败，请稍后再试。", 502) from exc
        return _extract_content(response.choices[0].message.content), context

    return _chat_via_http(api_key, payload), context
