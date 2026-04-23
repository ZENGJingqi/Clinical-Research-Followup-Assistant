from datetime import timedelta

from django.utils import timezone

from .models import ResearchProject, UserProfile


def get_user_profile(user):
    if not user.is_authenticated:
        return None
    cached_profile = getattr(user, "_followup_profile_cache", None)
    if cached_profile is not None:
        return cached_profile
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role": UserProfile.ROLE_NORMAL,
                "modify_window_days": UserProfile.default_modify_window_days(
                    UserProfile.ROLE_NORMAL
                ),
            },
        )
    user._followup_profile_cache = profile
    return profile


def get_user_role(user):
    profile = get_user_profile(user)
    return profile.role if profile else None


def get_user_role_label(user):
    profile = get_user_profile(user)
    return profile.get_role_display() if profile else None


def is_root(user):
    return get_user_role(user) == UserProfile.ROLE_ROOT


def is_admin(user):
    return get_user_role(user) in {UserProfile.ROLE_ROOT, UserProfile.ROLE_ADMIN}


def is_normal(user):
    return get_user_role(user) == UserProfile.ROLE_NORMAL


def can_manage_accounts(user):
    return is_root(user)


def can_export_data(user):
    return is_admin(user)


def can_export_project_data(user):
    return is_admin(user)


def can_manage_reference_data(user):
    return is_admin(user)


def can_manage_project_module(user):
    return get_user_role(user) in {UserProfile.ROLE_ROOT, UserProfile.ROLE_ADMIN, UserProfile.ROLE_NORMAL}


def can_manage_project_definition(user):
    return is_root(user)


def get_project_queryset_for_user(user, queryset=None):
    base_queryset = queryset if queryset is not None else ResearchProject.objects.all()
    role = get_user_role(user)
    if role == UserProfile.ROLE_ROOT:
        return base_queryset
    if role not in {UserProfile.ROLE_ADMIN, UserProfile.ROLE_NORMAL}:
        return base_queryset.none()
    profile = get_user_profile(user)
    allowed_ids = profile.allowed_projects.values_list("id", flat=True) if profile else []
    return base_queryset.filter(id__in=allowed_ids)


def can_access_project(user, project):
    if not can_manage_project_module(user):
        return False
    return get_project_queryset_for_user(user).filter(pk=project.pk).exists()


def get_modify_window_days(user):
    profile = get_user_profile(user)
    return profile.effective_modify_window_days if profile else None


def can_modify_record(user, obj):
    if is_root(user):
        return True
    if get_user_role(user) not in {UserProfile.ROLE_ADMIN, UserProfile.ROLE_NORMAL}:
        return False
    created_at = getattr(obj, "created_at", None)
    if not created_at:
        return False
    modify_window_days = get_modify_window_days(user)
    if not modify_window_days:
        return False
    cutoff = timezone.now() - timedelta(days=modify_window_days)
    return created_at >= cutoff
