"""Fixed-layout Short Bond/A4 OMR scanner."""
from pathlib import Path
import cv2
import numpy as np

DPI=300
PX_PER_MM=DPI/25.4
PAPER_CONFIG={
    "A4":{"canvas":(2480,3508),"markers":[(14,14),(196,14),(196,283),(14,283)],
          "first_y":75,"row_spacing":8,"sample_radius":24,
          "left_x":{"A":45,"B":55,"C":65,"D":75},"right_x":{"A":135,"B":145,"C":155,"D":165},
          "max_questions":50},
    "SHORT":{"canvas":(2550,3300),"markers":[(12,12),(203.9,12),(203.9,267.4),(12,267.4)],
             "first_y":38.8,"row_spacing":8.05,"sample_radius":20,
             "left_x":{"A":22.6,"B":28.3,"C":33.9,"D":39.5,"E":45.1},
             "right_x":{"A":57.8,"B":63.4,"C":69.0,"D":74.6,"E":80.2},
             "max_questions":60},
    "HALF_LETTER":{"canvas":(1650,2550),"markers":[(8,8),(132,8),(132,208),(8,208)],
             "first_y":52.2,"row_spacing":6.4,"sample_radius":20,
             "left_x":{"A":54,"B":64,"C":74,"D":84},"right_x":{"A":54,"B":64,"C":74,"D":84},
             "max_questions":25},
}
CHOICES=("A","B","C","D","E")
MIN_BUBBLE_SCORE=.24
MULTIPLE_RELATIVE_SCORE=.68
AMBIGUITY_GAP=.07
MARKER_POSITION_TOLERANCE_PX=30

class OMRScanError(Exception): pass

def _config(paper_size):
    key=str(paper_size or "A4").upper()
    if key in {"SHORT BOND","SHORT_BOND","LETTER"}: key="SHORT"
    if key in {"HALF LETTER","HALF-LETTER","HALF_LETTER","HALF"}: key="HALF_LETTER"
    if key not in PAPER_CONFIG: raise OMRScanError("Unsupported answer-sheet size.")
    return key,PAPER_CONFIG[key]

def mm_to_px(value): return round(value*PX_PER_MM)

def bubble_center(question_number,choice,paper_size="A4"):
    key,c=_config(paper_size)
    if not 1<=question_number<=c["max_questions"] or choice not in CHOICES:
        raise ValueError("Invalid OMR coordinate.")
    if key == "SHORT":
        group=(question_number-1)//20
        row=(question_number-1)%20
        xs={"left_x":c["left_x"],"middle_x":c["right_x"],"right_x":{"A":92.4,"B":98.0,"C":103.6,"D":109.2,"E":114.8}}[["left_x","middle_x","right_x"][group]]
    else:
        row=question_number-1 if key=="HALF_LETTER" or question_number<=25 else question_number-26
        xs=c["left_x"] if key=="HALF_LETTER" or question_number<=25 else c["right_x"]
    return mm_to_px(xs[choice]),mm_to_px(c["first_y"]+row*c["row_spacing"])

def _marker_centers(paper_size):
    _,c=_config(paper_size)
    return np.float32([[x*PX_PER_MM,y*PX_PER_MM] for x,y in c["markers"]])

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
        _,_,bw,bh=cv2.boundingRect(poly); ratio=bw/max(bh,1); fill=area/max(bw*bh,1)
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

def _warp(image,markers,paper_size):
    dst0=_marker_centers(paper_size)
    dst=np.float32([dst0[0],dst0[1],dst0[3],dst0[2]])
    matrix=cv2.getPerspectiveTransform(markers,dst)
    _,c=_config(paper_size)
    warped=cv2.warpPerspective(image,matrix,c["canvas"])
    projected=cv2.perspectiveTransform(markers.reshape(-1,1,2),matrix).reshape(-1,2)
    errors=np.linalg.norm(projected-dst,axis=1)
    if float(errors.max())>MARKER_POSITION_TOLERANCE_PX:
        raise OMRScanError("Perspective correction error is too large.")
    return warped

def _validate_warp(warped,paper_size):
    _,c=_config(paper_size)
    expected=(c["canvas"][1],c["canvas"][0])
    if warped.shape[:2]!=expected: raise OMRScanError("Invalid canonical page size.")
    gray=cv2.cvtColor(warped,cv2.COLOR_BGR2GRAY); scores=[]
    for cx,cy in _marker_centers(paper_size):
        r=35
        roi=gray[max(0,int(cy-r)):min(gray.shape[0],int(cy+r)),
                 max(0,int(cx-r)):min(gray.shape[1],int(cx+r))]
        if roi.size==0: raise OMRScanError("Registration marker region is missing.")
        darkness=1-float(np.mean(roi))/255
        scores.append(darkness)
        if darkness<.45: raise OMRScanError("A registration marker is not visible.")
    return round(float(np.mean(scores))*100,2)

def _bubble_score(gray,cx,cy,paper_size):
    """Measure only the inside of a bubble, excluding its outline."""
    _,c=_config(paper_size)
    r=c["sample_radius"]
    roi=gray[cy-r:cy+r+1,cx-r:cx+r+1]
    if roi.size==0:
        return 0.0

    # The printed circle border is dark even when the answer is empty.
    # Sampling the full bubble therefore makes every empty option look marked.
    # Use a small central core. This avoids the printed outline and also
    # reduces bleed/shadow from a neighboring bubble.
    inner=max(5,int(r*0.38))
    yy,xx=np.ogrid[-r:r+1,-r:r+1]
    mask=(xx*xx+yy*yy)<=inner*inner
    inner_pixels=roi[mask]

    # Use a robust statistic instead of the whole-circle average. Pencil/pen
    # marks should make the center substantially darker than clean paper.
    darkness=1.0-(float(np.percentile(inner_pixels,35))/255.0)
    return max(0.0,min(1.0,darkness))

def _read_question(gray,n,paper_size):
    scores={c:round(_bubble_score(gray,*bubble_center(n,c,paper_size),paper_size),4) for c in CHOICES}
    ranked=sorted(scores.items(),key=lambda x:x[1],reverse=True)
    top,top_score=ranked[0]; second,second_score=ranked[1]
    marked=[c for c,s in ranked if s>=MIN_BUBBLE_SCORE]

    # A second bubble must be independently strong, not merely above a low
    # absolute threshold. This prevents light print/shadow/noise in adjacent
    # bubbles from turning a single marked answer into "multiple".
    strong=[c for c,s in ranked if s>=MIN_BUBBLE_SCORE and s>=top_score*MULTIPLE_RELATIVE_SCORE]

    if top_score<MIN_BUBBLE_SCORE:
        status,selected,confidence="blank",None,0
    elif len(strong)>1:
        status,selected,confidence="multiple",None,min(100,second_score*100)
    elif top_score-second_score<AMBIGUITY_GAP:
        status,selected,confidence="unclear",None,max(0,(top_score-second_score)*100)
    else:
        status,selected,confidence="detected",top,min(100,(top_score-second_score)*100+top_score*50)
    return {"selected_choice":selected,"detected_choices":marked,"status":status,
            "confidence":round(confidence,2),"darkness_scores":scores}

def scan_answer_sheet(image_path,quiz,paper_size="A4"):
    key,c=_config(paper_size)
    if not Path(image_path).exists(): raise OMRScanError("Uploaded image was not found.")
    image=cv2.imread(image_path)
    if image is None: raise OMRScanError("OpenCV could not decode the image.")
    questions=list(quiz.questions.all())
    if not questions: raise OMRScanError("This quiz has no questions.")
    if len(questions)>c["max_questions"]: raise OMRScanError(f"{key} answer sheet supports at most {c['max_questions']} questions.")
    if key == "HALF_LETTER" and any(q.number>25 for q in questions):
        raise OMRScanError(f"{key} answer sheets use question numbers 1–25.")
    markers=_select_four(_find_marker_candidates(image))
    warped=_warp(image,markers,key)
    geometry_confidence=_validate_warp(warped,key)
    gray=cv2.GaussianBlur(cv2.cvtColor(warped,cv2.COLOR_BGR2GRAY),(3,3),0)
    answers=[]; score=0; needs_review=False
    for q in questions:
        d=_read_question(gray,q.number,key); status=d["status"]; selected=d["selected_choice"]
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
            "message":f"{key} scan completed. Some answers require teacher review." if needs_review else f"{key} scan completed successfully.",
            "paper_size":key}
