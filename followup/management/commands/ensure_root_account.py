from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from followup.models import UserProfile


class Command(BaseCommand):
    help = "确保存在一个 Root 账号"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="root")
        parser.add_argument("--password", default="Bucm@G209")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        user, created = User.objects.get_or_create(username=username, defaults={"is_active": True})
        user.set_password(password)
        user.is_active = True
        user.save()

        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.ROLE_ROOT},
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Root 账号 {username} 已创建。"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Root 账号 {username} 已更新密码并保持可用。"))
