"""Fixed-layout 50-question A4 OMR scanner."""
from pathlib import Path
import cv2
import numpy as np

DPI=300
PX_PER_MM=DPI/25.4
CANVAS_SIZE=(2480,3508)
MARKER_CENTERS=np.float32([[14*PX_PER_MM,14*PX_PER_MM],[196*PX_PER_MM,14*PX_PER_MM],
 [196*PX_PER_MM,283*PX_PER_MM],[14*PX_PER_MM,283*PX_PER_MM]])
LEFT_X_MM={"A":45,"B":55,"C":65,"D":75}
RIGHT_X_MM={"A":135,"B":145,"C":155,"D":165}
CHOICES=("A","B","C","D")
FIRST_ROW_Y_MM=75
ROW_SPACING_MM=8
BUBBLE_SAMPLE_RADIUS_PX=24
MIN_BUBBLE_SCORE=.18
AMBIGUITY_GAP=.07
MARKER_POSITION_TOLERANCE_PX=30

class OMRScanError(Exception): pass

def mm_to_px(value): return round(value*PX_PER_MM)

def bubble_center(question_number,choice):
    if not 1<=question_number<=50 or choice not in CHOICES: raise ValueError("Invalid OMR coordinate.")
    xs=LEFT_X_MM if question_number<=25 else RIGHT_X_MM
    row=question_number-1 if question_number<=25 else question_number-26
    return mm_to_px(xs[choice]),mm_to_px(FIRST_ROW_Y_MM+row*ROW_SPACING_MM)

def _find_marker_candidates(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    _,th=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    th=cv2.morphologyEx(th,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(th,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    h,w=gray.shape; page_area=h*w; out=[]
    for c in contours:
        area=cv2.contourArea(c)
        if area<page_area*.00015 or area>page_area*.03: continue
        peri=cv2.arcLength(c,True)
        if not peri: continue
        poly=cv2.approxPolyDP(c,.04*peri,True)
        if len(poly)!=4 or not cv2.isContourConvex(poly): continue
        x,y,bw,bh=cv2.boundingRect(poly); ratio=bw/max(bh,1); fill=area/max(bw*bh,1)
        if .70<=ratio<=1.30 and fill>=.55:
            out.append(poly.reshape(4,2).mean(axis=0).astype(np.float32))
    return out

def _select_four(candidates):
    if len(candidates)<4: raise OMRScanError("Could not detect all four registration markers.")
    pts=np.asarray(candidates,dtype=np.float32)
    tl=pts[np.argmin(pts[:,0]+pts[:,1])]
    tr=pts[np.argmax(pts[:,0]-pts[:,1])]
    br=pts[np.argmax(pts[:,0]+pts[:,1])]
    bl=pts[np.argmin(pts[:,0]-pts[:,1])]
    corners=np.array([tl,tr,br,bl],dtype=np.float32)
    if len({tuple(np.round(p,1)) for p in corners})!=4: raise OMRScanError("Registration markers are ambiguous.")
    top=np.linalg.norm(tr-tl); bottom=np.linalg.norm(br-bl); left=np.linalg.norm(bl-tl); right=np.linalg.norm(br-tr)
    if min(top,bottom,left,right)<=0 or max(top,bottom)/min(top,bottom)>1.5 or max(left,right)/min(left,right)>1.5:
        raise OMRScanError("Registration-marker geometry is invalid.")
    return corners

def _warp(image,markers):
    dst=np.float32([MARKER_CENTERS[0],MARKER_CENTERS[1],MARKER_CENTERS[3],MARKER_CENTERS[2]])
    matrix=cv2.getPerspectiveTransform(markers,dst)
    warped=cv2.warpPerspective(image,matrix,CANVAS_SIZE)
    projected=cv2.perspectiveTransform(markers.reshape(-1,1,2),matrix).reshape(-1,2)
    errors=np.linalg.norm(projected-dst,axis=1)
    if float(errors.max())>MARKER_POSITION_TOLERANCE_PX: raise OMRScanError("Perspective correction error is too large.")
    return warped

def _validate_warp(warped):
    if warped.shape[:2]!=(3508,2480): raise OMRScanError("Invalid canonical page size.")
    gray=cv2.cvtColor(warped,cv2.COLOR_BGR2GRAY); scores=[]
    for cx,cy in MARKER_CENTERS:
        x1,y1=int(cx-35),int(cy-35); x2,y2=int(cx+35),int(cy+35)
        roi=gray[y1:y2,x1:x2]
        if roi.size==0: raise OMRScanError("Registration marker region is missing.")
        darkness=1-float(np.mean(roi))/255
        scores.append(darkness)
        if darkness<.45: raise OMRScanError("A registration marker is not visible.")
    return round(float(np.mean(scores))*100,2)

def _bubble_score(gray,cx,cy):
    r=BUBBLE_SAMPLE_RADIUS_PX
    roi=gray[cy-r:cy+r+1,cx-r:cx+r+1]
    if roi.size==0:return 0
    yy,xx=np.ogrid[-r:r+1,-r:r+1]; mask=(xx*xx+yy*yy)<=r*r
    return float(1-np.mean(roi[mask])/255)

def _read_question(gray,n):
    scores={c:round(_bubble_score(gray,*bubble_center(n,c)),4) for c in CHOICES}
    ranked=sorted(scores.items(),key=lambda x:x[1],reverse=True)
    marked=[c for c,s in ranked if s>=MIN_BUBBLE_SCORE]
    top,top_score=ranked[0]; second_score=ranked[1][1]
    if not marked: status,selected,confidence="blank",None,0
    elif len(marked)>1: status,selected,confidence="multiple",None,min(100,top_score*100)
    elif top_score-second_score<AMBIGUITY_GAP: status,selected,confidence="unclear",None,max(0,(top_score-second_score)*100)
    else: status,selected,confidence="detected",top,min(100,(top_score-second_score)*100+top_score*50)
    return {"selected_choice":selected,"detected_choices":marked,"status":status,
            "confidence":round(confidence,2),"darkness_scores":scores}

def scan_answer_sheet(image_path,quiz):
    if not Path(image_path).exists(): raise OMRScanError("Uploaded image was not found.")
    image=cv2.imread(image_path)
    if image is None: raise OMRScanError("OpenCV could not decode the image.")
    questions=list(quiz.questions.all())
    if not questions: raise OMRScanError("This quiz has no questions.")
    if len(questions)>50: raise OMRScanError("The fixed A4 sheet supports at most 50 questions.")
    markers=_select_four(_find_marker_candidates(image))
    warped=_warp(image,markers)
    geometry_confidence=_validate_warp(warped)
    gray=cv2.GaussianBlur(cv2.cvtColor(warped,cv2.COLOR_BGR2GRAY),(3,3),0)
    answers=[]; score=0; needs_review=False
    for q in questions:
        d=_read_question(gray,q.number); status=d["status"]; selected=d["selected_choice"]
        if status=="detected":
            status="correct" if selected==q.correct_choice else "incorrect"
            correct=status=="correct"; score+=int(correct)
        else: correct=False; needs_review=True
        answers.append({"question":q,"selected_choice":selected,"detected_choices":d["detected_choices"],
                        "is_correct":correct,"confidence":d["confidence"],"status":status,
                        "darkness_scores":d["darkness_scores"]})
    total=len(answers); percentage=round(score/total*100,2) if total else 0
    return {"answers":answers,"score":score,"total_items":total,"percentage":percentage,
            "needs_review":needs_review,"geometry_confidence":geometry_confidence,
            "message":"Scan completed. Some answers require teacher review." if needs_review else "Scan completed successfully."}
