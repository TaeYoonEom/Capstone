# main/migrations/0020_add_fulltext_affiliation_name.py
from django.db import migrations

CREATE = "CREATE FULLTEXT INDEX ft_aff_name ON affiliation (name);"
DROP   = "DROP INDEX ft_aff_name ON affiliation;"

def forwards(apps, schema_editor):
    # MySQL/MariaDB에서만 Fulltext 수행
    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cur:
            cur.execute(CREATE)

def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cur:
            try:
                cur.execute(DROP)
            except Exception:
                pass

class Migration(migrations.Migration):
    # ⬇⬇ '직전 정상 마이그레이션' 이름으로 바꾸세요.
    # 예: 0019_add_covering_indexes 가 맞다면 그대로 두고,
    # 다르면 'python manage.py showmigrations main'로 마지막 이름 확인해서 수정
    dependencies = [
        ('main', '0019_add_covering_indexes'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]