from decimal import Decimal
from django.core.files.uploadedfile import UploadedFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from .models import Answer, Quiz, Submission
from .omr import OMRScanError, scan_answer_sheet

def home(request):
    quizzes=Quiz.objects.filter(is_active=True).prefetch_related("questions")
    return render(request,"app/home.html",{"quizzes":quizzes})

def quiz_detail(request,quiz_id):
    quiz=get_object_or_404(Quiz.objects.prefetch_related("questions"),pk=quiz_id)
    return render(request,"app/quiz_detail.html",{"quiz":quiz})

def print_sheet(request,quiz_id):
    quiz=get_object_or_404(Quiz.objects.prefetch_related("questions"),pk=quiz_id)
    return render(request,"app/print_sheet.html",{"quiz":quiz})

def camera_scan(request,quiz_id):
    quiz=get_object_or_404(Quiz.objects.prefetch_related("questions"),pk=quiz_id)
    return render(request,"app/camera_scan.html",{"quiz":quiz})

@require_POST
def camera_submit(request,quiz_id):
    quiz=get_object_or_404(Quiz.objects.prefetch_related("questions"),pk=quiz_id)
    image=request.FILES.get("image")
    if not isinstance(image,UploadedFile):
        return JsonResponse({"ok":False,"error":"No answer-sheet image was uploaded."},status=400)
    if image.size>15*1024*1024:
        return JsonResponse({"ok":False,"error":"Image is too large. Maximum is 15 MB."},status=400)
    submission=Submission.objects.create(quiz=quiz,user=request.user if request.user.is_authenticated else None,
        student_name=request.POST.get("student_name","").strip(),student_id=request.POST.get("student_id","").strip(),
        answer_sheet=image,total_items=quiz.total_questions)
    try:
        result=scan_answer_sheet(submission.answer_sheet.path,quiz)
    except OMRScanError as exc:
        submission.status=Submission.STATUS_ERROR; submission.scan_message=str(exc); submission.save(update_fields=["status","scan_message"])
        return JsonResponse({"ok":False,"submission_id":submission.id,"status":submission.status,"error":str(exc)},status=422)
    except Exception:
        submission.status=Submission.STATUS_ERROR; submission.scan_message="The scanner encountered an unexpected processing error."
        submission.save(update_fields=["status","scan_message"])
        return JsonResponse({"ok":False,"submission_id":submission.id,"status":submission.status,"error":"The scanner could not process this image."},status=500)
    for item in result["answers"]:
        Answer.objects.create(submission=submission,question=item["question"],selected_choice=item["selected_choice"],
            detected_choices=",".join(item["detected_choices"]),is_correct=item["is_correct"],
            confidence=Decimal(str(round(item["confidence"],2))),status=item["status"],darkness_scores=item["darkness_scores"])
    submission.score=result["score"]; submission.total_items=result["total_items"]; submission.percentage=Decimal(str(result["percentage"]))
    submission.geometry_confidence=Decimal(str(result["geometry_confidence"]))
    submission.status=Submission.STATUS_REVIEW if result["needs_review"] else Submission.STATUS_GRADED
    submission.scan_message=result["message"]
    submission.save(update_fields=["score","total_items","percentage","geometry_confidence","status","scan_message"])
    return JsonResponse({"ok":True,"submission_id":submission.id,"redirect_url":f"/submission/{submission.id}/result/"})

def result(request,submission_id):
    submission=get_object_or_404(Submission.objects.select_related("quiz").prefetch_related("answers__question"),pk=submission_id)
    return render(request,"app/result.html",{"submission":submission})
