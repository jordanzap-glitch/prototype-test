from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Quiz", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=200)), ("description", models.TextField(blank=True)),
            ("instructions", models.TextField(blank=True)), ("is_active", models.BooleanField(default=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ], options={"ordering":["-created_at"]}),
        migrations.CreateModel(name="Question", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("number", models.PositiveIntegerField()), ("text", models.TextField()),
            ("choice_a", models.CharField(max_length=500)), ("choice_b", models.CharField(max_length=500)),
            ("choice_c", models.CharField(max_length=500)), ("choice_d", models.CharField(max_length=500)),
            ("correct_choice", models.CharField(choices=[("A","A"),("B","B"),("C","C"),("D","D")], max_length=1)),
            ("quiz", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="app.quiz")),
        ], options={"ordering":["number"]}),
        migrations.CreateModel(name="Submission", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("student_name", models.CharField(blank=True, max_length=200)), ("student_id", models.CharField(blank=True, max_length=100)),
            ("answer_sheet", models.ImageField(upload_to="answer_sheets/%Y/%m/")), ("score", models.PositiveIntegerField(default=0)),
            ("total_items", models.PositiveIntegerField(default=0)), ("percentage", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
            ("status", models.CharField(choices=[("processing","Processing"),("graded","Graded"),("needs_review","Needs Review"),("scan_error","Scan Error")], default="processing", max_length=20)),
            ("scan_message", models.TextField(blank=True)), ("geometry_confidence", models.DecimalField(decimal_places=2, default=0)),
            ("submitted_at", models.DateTimeField(auto_now_add=True)),
            ("quiz", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="submissions", to="app.quiz")),
            ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="omr_submissions", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering":["-submitted_at"]}),
        migrations.CreateModel(name="Answer", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("selected_choice", models.CharField(blank=True, max_length=1, null=True)), ("detected_choices", models.CharField(blank=True, max_length=10)),
            ("is_correct", models.BooleanField(default=False)), ("confidence", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
            ("status", models.CharField(choices=[("correct","Correct"),("incorrect","Incorrect"),("blank","Blank"),("multiple","Multiple Mark"),("unclear","Unclear")], default="unclear", max_length=12)),
            ("darkness_scores", models.JSONField(blank=True, default=dict)),
            ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scanned_answers", to="app.question")),
            ("submission", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answers", to="app.submission")),
        ], options={"ordering":["question__number"]}),
        migrations.AddConstraint(model_name="question", constraint=models.UniqueConstraint(fields=("quiz","number"), name="unique_question_number_per_quiz")),
        migrations.AddConstraint(model_name="answer", constraint=models.UniqueConstraint(fields=("submission","question"), name="unique_answer_per_submission_question")),
    ]
