from django.db import migrations


def consolidate(apps, schema_editor):
    """BR-001: 강의는 1행만. 과거 코드가 제목으로 get_or_create 하면서 유령 Lecture가
    생겼을 수 있다 → id 최솟값 행으로 모든 Lesson을 옮기고 나머지 Lecture는 삭제한다."""
    Lecture = apps.get_model("core", "Lecture")
    Lesson = apps.get_model("core", "Lesson")

    keep = Lecture.objects.order_by("id").first()
    if keep is None:
        return

    extras = Lecture.objects.exclude(pk=keep.pk)
    moved = Lesson.objects.filter(lecture__in=extras).update(lecture=keep)
    deleted, _ = extras.delete()
    if moved or deleted:
        print(f"  · Lesson {moved}건을 Lecture#{keep.pk}로 이동, 유령 Lecture 정리")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_lesson_updated_at"),
    ]

    operations = [
        migrations.RunPython(consolidate, noop),
    ]
