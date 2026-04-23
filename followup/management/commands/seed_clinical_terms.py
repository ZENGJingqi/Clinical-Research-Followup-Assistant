from django.core.management.base import BaseCommand

from followup.models import ClinicalTerm


COMMON_TERMS = {
    ClinicalTerm.CATEGORY_HERB: [
        ("黄芪", "北芪"),
        ("党参", "潞党参"),
        ("白术", "炒白术"),
        ("茯苓", "云苓,白茯苓"),
        ("甘草", "炙甘草,生甘草"),
        ("当归", "全当归"),
        ("川芎", "芎藭"),
        ("白芍", "炒白芍"),
        ("熟地黄", "熟地"),
        ("陈皮", "橘皮"),
        ("半夏", "法半夏,姜半夏"),
        ("麦冬", "麦门冬"),
        ("丹参", "紫丹参"),
        ("泽泻", "建泽泻"),
        ("柴胡", "北柴胡"),
        ("砂仁", "春砂仁"),
        ("木香", "广木香"),
        ("枳壳", ""),
        ("厚朴", "川朴"),
        ("藿香", "广藿香"),
        ("佩兰", ""),
        ("苍术", "炒苍术"),
        ("山药", "淮山药"),
        ("薏苡仁", "薏仁"),
        ("莲子", "莲子肉"),
        ("扁豆", "白扁豆"),
        ("神曲", "六神曲"),
        ("麦芽", "炒麦芽"),
        ("谷芽", "炒谷芽"),
        ("鸡内金", "鸡肫皮"),
        ("山楂", "焦山楂"),
        ("莱菔子", "萝卜子"),
        ("黄连", ""),
        ("吴茱萸", ""),
        ("干姜", ""),
    ],
    ClinicalTerm.CATEGORY_TCM_DISEASE: [
        ("眩晕", ""),
        ("胸痹", ""),
        ("心悸", ""),
        ("不寐", "失眠"),
        ("郁病", "郁证"),
        ("头痛", ""),
        ("胃脘痛", "胃痛"),
        ("消渴", ""),
        ("咳嗽", ""),
        ("泄泻", "腹泻"),
        ("便秘", ""),
        ("虚劳", ""),
        ("胃痞", "痞满"),
        ("嘈杂", ""),
        ("呕吐", ""),
        ("噎膈", ""),
        ("反酸", ""),
        ("腹痛", ""),
        ("纳呆", ""),
        ("食积", ""),
    ],
    ClinicalTerm.CATEGORY_WESTERN_DISEASE: [
        ("高血压病", "原发性高血压"),
        ("2型糖尿病", "糖尿病"),
        ("冠心病", "冠状动脉粥样硬化性心脏病"),
        ("慢性胃炎", ""),
        ("功能性消化不良", ""),
        ("失眠障碍", "失眠"),
        ("焦虑状态", "焦虑障碍"),
        ("高脂血症", "血脂异常"),
        ("脂肪肝", "非酒精性脂肪性肝病"),
        ("偏头痛", ""),
        ("慢性支气管炎", ""),
        ("骨质疏松症", "骨质疏松"),
        ("慢性萎缩性胃炎", ""),
        ("慢性非萎缩性胃炎", ""),
        ("胃食管反流病", "反流性食管炎"),
        ("消化性溃疡", "胃溃疡,十二指肠溃疡"),
        ("肠易激综合征", "IBS"),
        ("慢性结肠炎", ""),
        ("功能性腹胀", ""),
        ("功能性便秘", ""),
    ],
    ClinicalTerm.CATEGORY_TREATMENT_PRINCIPLE: [
        ("益气健脾", ""),
        ("养血安神", ""),
        ("疏肝理气", ""),
        ("活血化瘀", ""),
        ("化痰祛湿", ""),
        ("滋阴清热", ""),
        ("温阳散寒", ""),
        ("平肝潜阳", ""),
        ("清热解毒", ""),
        ("补肾填精", ""),
        ("和胃降逆", ""),
        ("宁心安神", ""),
        ("健脾和胃", ""),
        ("消食导滞", ""),
        ("理气和中", ""),
        ("温中散寒", ""),
        ("清热燥湿", ""),
        ("降逆止呕", ""),
        ("疏肝和胃", ""),
        ("健脾渗湿", ""),
    ],
    ClinicalTerm.CATEGORY_PATHOGENESIS: [
        ("肝郁气滞", ""),
        ("脾虚湿盛", ""),
        ("气阴两虚", ""),
        ("痰湿中阻", ""),
        ("肝阳上亢", ""),
        ("瘀血阻络", ""),
        ("心脾两虚", ""),
        ("肝肾阴虚", ""),
        ("脾肾阳虚", ""),
        ("痰热内扰", ""),
        ("胃失和降", ""),
        ("气滞血瘀", ""),
        ("脾胃虚弱", ""),
        ("脾胃湿热", ""),
        ("寒热错杂", ""),
        ("饮食积滞", "食积内停"),
        ("肝胃不和", ""),
        ("脾胃气虚", ""),
        ("胃阴不足", ""),
        ("中焦虚寒", ""),
    ],
    ClinicalTerm.CATEGORY_SYMPTOM: [
        ("乏力", "疲乏"),
        ("头晕", "眩晕"),
        ("头痛", ""),
        ("胸闷", ""),
        ("胸痛", ""),
        ("心悸", "心慌"),
        ("失眠", "入睡困难,多梦易醒"),
        ("口干", ""),
        ("纳差", "食欲下降"),
        ("腹胀", ""),
        ("便溏", "大便稀"),
        ("便秘", "大便干结"),
        ("腰膝酸软", ""),
        ("畏寒", "怕冷"),
        ("潮热盗汗", ""),
        ("胃脘胀满", "胃胀"),
        ("胃脘隐痛", ""),
        ("反酸", "泛酸"),
        ("嗳气", "打嗝"),
        ("恶心", ""),
        ("呕吐", ""),
        ("早饱", ""),
        ("餐后腹胀", ""),
        ("肠鸣", ""),
        ("大便黏滞", ""),
    ],
}


def merge_alias_text(existing_alias, incoming_alias):
    values = []
    seen = set()
    for raw in [existing_alias or "", incoming_alias or ""]:
        for item in raw.split(","):
            text = item.strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append(text)
    return ",".join(values)


class Command(BaseCommand):
    help = "为各术语分类写入常见测试术语，并自动补充别名，当前偏脾胃病方向。"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for category, items in COMMON_TERMS.items():
            for name, alias in items:
                term, created = ClinicalTerm.objects.get_or_create(
                    category=category,
                    name=name,
                    defaults={
                        "alias": alias,
                        "is_active": True,
                    },
                )
                if created:
                    created_count += 1
                    continue

                merged_alias = merge_alias_text(term.alias, alias)
                changed_fields = []
                if merged_alias != (term.alias or ""):
                    term.alias = merged_alias
                    changed_fields.append("alias")
                if not term.is_active:
                    term.is_active = True
                    changed_fields.append("is_active")
                if changed_fields:
                    term.save(update_fields=changed_fields)
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"常见术语写入完成：新增 {created_count} 条，补充/复用 {updated_count} 条。"
            )
        )
