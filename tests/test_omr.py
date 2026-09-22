import cv2
import numpy as np
import pytest
from pathlib import Path
from django.test import TestCase
from app.models import Quiz, Question
from app.omr import OMRScanError, bubble_center, scan_answer_sheet, PAPER_CONFIG, _marker_centers, mm_to_px

def synthetic_sheet(fill=None, multiple=None, blur=0, glare=False):
    cfg=PAPER_CONFIG["A4"]
    canvas=cfg["canvas"]
    img=np.full((canvas[1],canvas[0],3),255,np.uint8)
    for x,y in _marker_centers("A4"):
        x,y=int(x),int(y); cv2.rectangle(img,(x-28,y-28),(x+28,y+28),(0,0,0),-1)
    for q in range(1,51):
        for choice in "ABCD":
            cx,cy=bubble_center(q,choice); cv2.circle(img,(cx,cy),mm_to_px(3.5),(0,0,0),2)
    for groups in (fill or {},multiple or {}):
        for q,choices in groups.items():
            for choice in choices:
                cx,cy=bubble_center(q,choice); cv2.circle(img,(cx,cy),mm_to_px(3.0),(0,0,0),-1)
    if glare:
        overlay=img.copy(); cv2.ellipse(overlay,(1240,1700),(520,280),-20,0,360,(255,255,255),-1); img=cv2.addWeighted(img,.45,overlay,.55,0)
    if blur: img=cv2.GaussianBlur(img,(blur|1,blur|1),0)
    return img

def save_tmp(tmp_path,img,name="scan.jpg"):
    path=tmp_path/name; assert cv2.imwrite(str(path),img); return str(path)

@pytest.fixture
def quiz(db):
    q=Quiz.objects.create(title="Synthetic Test Quiz")
    for n in range(1,51):
        Question.objects.create(quiz=q,number=n,text=f"Question {n}",choice_a="A",choice_b="B",choice_c="C",choice_d="D",correct_choice="A")
    return q

class TestOMRGeometry(TestCase):
    def test_coordinate_conversion(self):
        assert mm_to_px(25.4)==300
        assert bubble_center(1,"A")== (mm_to_px(45),mm_to_px(75))
        assert bubble_center(25,"D")== (mm_to_px(75),mm_to_px(267))
        assert bubble_center(26,"A")== (mm_to_px(135),mm_to_px(75))
        assert bubble_center(50,"D")== (mm_to_px(165),mm_to_px(267))

    def test_marker_detection_and_perspective_correction(self,tmp_path,quiz):
        src=synthetic_sheet(fill={1:["A"],2:["A"]}); h,w=src.shape[:2]
        src_pts=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
        dst_pts=np.float32([[150,90],[w-180,40],[w-80,h-120],[110,h-40]])
        warped=cv2.warpPerspective(src,cv2.getPerspectiveTransform(src_pts,dst_pts),(w,h))
        result=scan_answer_sheet(save_tmp(tmp_path,warped),quiz)
        assert result["geometry_confidence"]>45
        assert result["answers"][0]["selected_choice"]=="A"

    def test_cropped_page_rejected(self,tmp_path,quiz):
        path=save_tmp(tmp_path,synthetic_sheet()[120:,:-140])
        with pytest.raises(OMRScanError): scan_answer_sheet(path,quiz)

    def test_blank_answers_require_review(self,tmp_path,quiz):
        result=scan_answer_sheet(save_tmp(tmp_path,synthetic_sheet()),quiz)
        assert result["score"]==0 and result["needs_review"]
        assert all(a["status"]=="blank" for a in result["answers"])

    def test_multiple_marks_flagged(self,tmp_path,quiz):
        result=scan_answer_sheet(save_tmp(tmp_path,synthetic_sheet(multiple={1:["A","B"]})),quiz)
        assert result["answers"][0]["status"]=="multiple"
        assert result["needs_review"]

    def test_glare_requires_safe_handling(self,tmp_path,quiz):
        result=scan_answer_sheet(save_tmp(tmp_path,synthetic_sheet(fill={1:["A"]},glare=True)),quiz)
        assert result["needs_review"] or result["answers"][0]["status"]=="correct"

    def test_heavy_blur_requires_review_or_rejection(self,tmp_path,quiz):
        try:
            result=scan_answer_sheet(save_tmp(tmp_path,synthetic_sheet(fill={1:["A"]},blur=21)),quiz)
            assert result["needs_review"]
        except OMRScanError:
            pass

    def test_all_50_marked_a_grade_100(self,tmp_path,quiz):
        result=scan_answer_sheet(save_tmp(tmp_path,synthetic_sheet(fill={n:["A"] for n in range(1,51)})),quiz)
        assert result["score"]==50 and result["percentage"]==100 and not result["needs_review"]

def test_sample_scan_directory_is_optional():
    sample_dir=Path(__file__).resolve().parent/"sample_scans"
    if not sample_dir.exists(): pytest.skip("No sample scans checked into tests/sample_scans.")
    assert list(sample_dir.glob("*.jpg"))+list(sample_dir.glob("*.png"))
