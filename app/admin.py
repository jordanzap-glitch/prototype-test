from django.contrib import admin
from .models import Answer, Question, Quiz, Submission

class QuestionInline(admin.TabularInline):
    model=Question
    extra=1
    ordering=("number",)

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display=("title","total_questions_display","is_active","created_at")
    list_filter=("is_active",)
    search_fields=("title","description")
    inlines=[QuestionInline]
    @admin.display(description="Questions")
    def total_questions_display(self,obj): return obj.total_questions

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display=("quiz","student_name","student_id","score","percentage","status","submitted_at")
    list_filter=("status","quiz")
    search_fields=("student_name","student_id","quiz__title")
    readonly_fields=("score","total_items","percentage","geometry_confidence","submitted_at")

@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display=("submission","question","selected_choice","status","confidence","is_correct")
    list_filter=("status","is_correct")
    search_fields=("submission__student_name","submission__student_id")
