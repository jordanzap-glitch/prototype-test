from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("app", "0002_alter_submission_geometry_confidence"),
    ]
    operations = [
        migrations.AddField(
            model_name="question",
            name="choice_e",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AlterField(
            model_name="question",
            name="correct_choice",
            field=models.CharField(
                choices=[("A","A"),("B","B"),("C","C"),("D","D"),("E","E")],
                max_length=1,
            ),
        ),
    ]
