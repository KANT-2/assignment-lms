from django.db import migrations, models


def drop_existing_todos(apps, schema_editor):
    """TODO 를 달력 날짜 기반으로 전환 — 날짜 없는 기존 항목은 폐기(요구사항)."""
    apps.get_model("core", "Todo").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_consolidate_lectures"),
    ]

    operations = [
        migrations.RunPython(drop_existing_todos, migrations.RunPython.noop),
        migrations.AddField(
            model_name="todo",
            name="due_date",
            field=models.DateField(help_text="이 할 일을 배치한 날짜 (달력 연동)"),
        ),
        migrations.AddIndex(
            model_name="todo",
            index=models.Index(fields=["student_id", "due_date"], name="todo_student_due_idx"),
        ),
        migrations.AlterModelOptions(
            name="todo",
            options={"ordering": ["is_done", "-created_at"]},
        ),
    ]
