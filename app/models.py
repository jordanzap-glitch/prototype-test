from django.conf import settings
from django.db import models

class Quiz(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-created_at"]
    def __str__(self): return self.title
    @property
    def total_questions(self): return self.questions.count()

class Question(models.Model):
    CHOICES = [("A","A"),("B","B"),("C","C"),("D","D")]
    quiz = models.ForeignKey(Quiz,on_delete=models.CASCADE,related_name="questions")
    number = models.PositiveIntegerField()
    text = models.TextField()
    choice_a = models.CharField(max_length=500)
    choice_b = models.CharField(max_length=500)
    choice_c = models.CharField(max_length=500)
    choice_d = models.CharField(max_length=500)
    correct_choice = models.CharField(max_length=1,choices=CHOICES)
    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["quiz","number"],name="unique_question_number_per_quiz")]
    def __str__(self): return f"{self.quiz.title} - Q{self.number}"

class Submission(models.Model):
    STATUS_PROCESSING="processing"; STATUS_GRADED="graded"; STATUS_REVIEW="needs_review"; STATUS_ERROR="scan_error"
    STATUS_CHOICES=[(STATUS_PROCESSING,"Processing"),(STATUS_GRADED,"Graded"),(STATUS_REVIEW,"Needs Review"),(STATUS_ERROR,"Scan Error")]
    quiz=models.ForeignKey(Quiz,on_delete=models.CASCADE,related_name="submissions")
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name="omr_submissions")
    student_name=models.CharField(max_length=200,blank=True)
    student_id=models.CharField(max_length=100,blank=True)
    answer_sheet=models.ImageField(upload_to="answer_sheets/%Y/%m/")
    score=models.PositiveIntegerField(default=0)
    total_items=models.PositiveIntegerField(default=0)
    percentage=models.DecimalField(max_digits=6,decimal_places=2,default=0)
    status=models.CharField(max_length=20,choices=STATUS_CHOICES,default=STATUS_PROCESSING)
    scan_message=models.TextField(blank=True)
    geometry_confidence=models.DecimalField(max_digits=5,decimal_places=2,default=0)
    submitted_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-submitted_at"]
    def __str__(self): return f"{self.quiz.title} - {self.student_name or 'Anonymous'} - {self.percentage}%"
    @property
    def needs_review(self): return self.status==self.STATUS_REVIEW

class Answer(models.Model):
    STATUS_CHOICES=[("correct","Correct"),("incorrect","Incorrect"),("blank","Blank"),("multiple","Multiple Mark"),("unclear","Unclear")]
    submission=models.ForeignKey(Submission,on_delete=models.CASCADE,related_name="answers")
    question=models.ForeignKey(Question,on_delete=models.CASCADE,related_name="scanned_answers")
    selected_choice=models.CharField(max_length=1,blank=True,null=True)
    detected_choices=models.CharField(max_length=10,blank=True)
    is_correct=models.BooleanField(default=False)
    confidence=models.DecimalField(max_digits=5,decimal_places=2,default=0)
    status=models.CharField(max_length=12,choices=STATUS_CHOICES,default="unclear")
    darkness_scores=models.JSONField(default=dict,blank=True)
    class Meta:
        ordering=["question__number"]
        constraints=[models.UniqueConstraint(fields=["submission","question"],name="unique_answer_per_submission_question")]
    def __str__(self): return f"{self.submission_id} - Q{self.question.number}"
