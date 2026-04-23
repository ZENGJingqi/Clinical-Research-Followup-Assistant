from django.conf import settings

from .permissions import (
    can_export_data,
    can_manage_accounts,
    can_manage_project_module,
    can_manage_reference_data,
    get_user_role_label,
)


def app_context(request):
    return {
        "app_name": settings.APP_NAME,
        "current_user_role": get_user_role_label(request.user),
        "can_export_data": can_export_data(request.user),
        "can_manage_accounts": can_manage_accounts(request.user),
        "can_manage_project_module": can_manage_project_module(request.user),
        "can_manage_reference_data": can_manage_reference_data(request.user),
    }
