from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('main', '0001_initial'),  # 기존 마이그레이션 파일과 연결 (적절히 수정)
    ]

    operations = [
        migrations.RunSQL(
            """
            ALTER TABLE paper 
            ADD FULLTEXT INDEX ft_paper_title_abstract (title, abstract);
            """,

        ),
    ]
