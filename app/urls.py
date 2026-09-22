from django.urls import path
from . import views
app_name="app"
urlpatterns=[
 path("",views.home,name="home"),
 path("quiz/<int:quiz_id>/",views.quiz_detail,name="quiz_detail"),
 path("quiz/<int:quiz_id>/print/",views.print_sheet,name="print_sheet"),
 path("quiz/<int:quiz_id>/scan/",views.camera_scan,name="camera_scan"),
 path("quiz/<int:quiz_id>/scan/calibrate/",views.camera_calibrate,name="camera_calibrate"),
 path("quiz/<int:quiz_id>/scan/submit/",views.camera_submit,name="camera_submit"),
 path("submission/<int:submission_id>/result/",views.result,name="result"),
]
