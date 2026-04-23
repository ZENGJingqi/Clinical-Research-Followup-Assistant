from pathlib import Path

from django.core.management.base import BaseCommand

from followup.models import ClinicalTerm


class Command(BaseCommand):
    help = "从项目根目录的常用饮片目录和四诊术语文本导入专业术语。"

    def handle(self, *args, **options):
        project_root = Path(__file__).resolve().parents[3]
        imported = 0
        updated = 0

        sources = [
            (project_root / "常用饮片目录.txt", ClinicalTerm.CATEGORY_HERB),
        ]

        for path, category in sources:
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"未找到文件：{path.name}"))
                continue
            seen = set()
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    name = line.strip()
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    _, created = ClinicalTerm.objects.update_or_create(
                        category=category,
                        name=name,
                        defaults={"is_active": True},
                    )
                    if created:
                        imported += 1
                    else:
                        updated += 1

        self.stdout.write(self.style.SUCCESS(f"导入完成：新增 {imported} 条，更新 {updated} 条。"))
