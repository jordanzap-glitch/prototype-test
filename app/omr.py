"""Fixed-layout five-choice (A–E) OMR scanner.

All printable layouts and scanner coordinates are calibrated from the same
millimetre measurements. The four black corner markers define the page
perspective; answer bubbles are read from the canonical warped page.
"""
from pathlib import Path
import cv2
import numpy as np

DPI = 300
PX_PER_MM = DPI / 25.4

# Marker coordinates are CENTER points in millimetres and must match the
# printed marker centers in templates/app/print_sheet.html.
PAPER_CONFIG = {
    "A4": {
        "canvas": (2480, 3508),
        "markers": [(10, 10), (200, 10), (200, 287), (10, 287)],
        "first_y": 53.1,
        "row_spacing": 7.8,
        "sample_radius": 24,
        "columns": [
            {"A": 43.25, "B": 50.25, "C": 57.25, "D": 64.25, "E": 71.25},
            {"A": 133.25, "B": 140.25, "C": 147.25, "D": 154.25, "E": 161.25},
        ],
        "max_questions": 50,
    },
    "SHORT": {
        "canvas": (2550, 3300),
        "markers": [(7.5, 7.5), (208.4, 7.5), (208.4, 267), (7.5, 267)],
        "first_y": 43.75,
        "row_spacing": 7.25,
        "second_gap": 7.5,
        "sample_radius": 20,
        "columns": [
            {"A": 23.2, "B": 28.9, "C": 34.8, "D": 40.7, "E": 46.3},
            {"A": 58.9, "B": 64.7, "C": 70.6, "D": 76.4, "E": 82.1},
            {"A": 94.8, "B": 100.6, "C": 106.4, "D": 112.2, "E": 117.9},
        ],
        "max_questions": 60,
    },
    "LEGAL": {
        "canvas": (2550, 4200),
        "markers": [(10, 10), (205.9, 10), (205.9, 345.6), (10, 345.6)],
        "first_y": 53.0,
        "row_spacing": 7.55,
        "sample_radius": 20,
        "columns": [
            {"A": 27.9, "B": 34.7, "C": 41.5, "D": 48.3, "E": 55.1},
            {"A": 73.9, "B": 80.7, "C": 87.5, "D": 94.3, "E": 101.1},
            {"A": 119.9, "B": 126.7, "C": 133.5, "D": 140.3, "E": 147.1},
            {"A": 165.9, "B": 172.7, "C": 179.5, "D": 186.3, "E": 193.1},
        ],
        "max_questions": 100,
    },
    "HALF_LETTER": {
        "canvas": (1650, 2550),
        "markers": [(8, 8), (131.7, 8), (131.7, 207.9), (8, 207.9)],
        "first_y": 51.6,
        "row_spacing": 6.4,
        "sample_radius": 20,
        "left_x": {"A": 49, "B": 59, "C": 69, "D": 79, "E": 89},
        "max_questions": 25,
    },
}

CHOICES = ("A", "B", "C", "D", "E")
MIN_BUBBLE_SCORE = 0.24
MULTIPLE_RELATIVE_SCORE = 0.68
AMBIGUITY_GAP = 0.07
MARKER_POSITION_TOLERANCE_PX = 30


class OMRScanError(Exception):
    pass


def _config(paper_size):
    key = str(paper_size or "A4").upper()
    if key in {"SHORT BOND", "SHORT_BOND", "LETTER"}:
        key = "SHORT"
    if key in {"HALF LETTER", "HALF-LETTER", "HALF_LETTER", "HALF"}:
        key = "HALF_LETTER"
    if key not in PAPER_CONFIG:
        raise OMRScanError("Unsupported answer-sheet size.")
    return key, PAPER_CONFIG[key]


def mm_to_px(value):
    return round(value * PX_PER_MM)


def bubble_center(question_number, choice, paper_size="A4"):
    key, c = _config(paper_size)
    if not 1 <= question_number <= c["max_questions"] or choice not in CHOICES:
        raise ValueError("Invalid OMR coordinate.")

    if key == "LEGAL":
        group = (question_number - 1) // 25
        row = (question_number - 1) % 25
        xs = c["columns"][group]
        return mm_to_px(xs[choice]), mm_to_px(c["first_y"] + row * c["row_spacing"])

    if key == "SHORT":
        group = (question_number - 1) // 20
        row = (question_number - 1) % 20
        y = c["first_y"] + row * c["row_spacing"]
        if row >= 10:
            y += c["second_gap"]
        xs = c["columns"][group]
        return mm_to_px(xs[choice]), mm_to_px(y)

    if key == "HALF_LETTER":
        row = question_number - 1
        return mm_to_px(c["left_x"][choice]), mm_to_px(c["first_y"] + row * c["row_spacing"])

    group = (question_number - 1) // 25
    row = (question_number - 1) % 25
    xs = c["columns"][group]
    return mm_to_px(xs[choice]), mm_to_px(c["first_y"] + row * c["row_spacing"])


def _marker_centers(paper_size):
    _, c = _config(paper_size)
    return np.float32([[x * PX_PER_MM, y * PX_PER_MM] for x, y in c["markers"]])


def _find_marker_candidates(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(th, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    h, w = gray.shape
    page_area = h * w
    out = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < page_area * 0.00015 or area > page_area * 0.03:
            continue
        peri = cv2.arcLength(contour, True)
        if not peri:
            continue
        poly = cv2.approxPolyDP(contour, 0.04 * peri, True)
        if len(poly) != 4 or not cv2.isContourConvex(poly):
            continue
        _, _, bw, bh = cv2.boundingRect(poly)
        ratio = bw / max(bh, 1)
        fill = area / max(bw * bh, 1)
        if 0.70 <= ratio <= 1.30 and fill >= 0.55:
            out.append(poly.reshape(4, 2).mean(axis=0).astype(np.float32))
    return out


def _select_four(candidates):
    if len(candidates) < 4:
        raise OMRScanError("Could not detect all four registration markers.")
    pts = np.asarray(candidates, dtype=np.float32)
    tl = pts[np.argmin(pts[:, 0] + pts[:, 1])]
    tr = pts[np.argmax(pts[:, 0] - pts[:, 1])]
    br = pts[np.argmax(pts[:, 0] + pts[:, 1])]
    bl = pts[np.argmin(pts[:, 0] - pts[:, 1])]
    corners = np.array([tl, tr, br, bl], dtype=np.float32)

    if len({tuple(np.round(p, 1)) for p in corners}) != 4:
        raise OMRScanError("Registration markers are ambiguous.")

    top = np.linalg.norm(tr - tl)
    bottom = np.linalg.norm(br - bl)
    left = np.linalg.norm(bl - tl)
    right = np.linalg.norm(br - tr)
    if min(top, bottom, left, right) <= 0:
        raise OMRScanError("Registration-marker geometry is invalid.")
    if max(top, bottom) / min(top, bottom) > 1.5 or max(left, right) / min(left, right) > 1.5:
        raise OMRScanError("Registration-marker geometry is invalid.")
    return corners


def _warp(image, markers, paper_size):
    dst0 = _marker_centers(paper_size)
    dst = np.float32([dst0[0], dst0[1], dst0[3], dst0[2]])
    matrix = cv2.getPerspectiveTransform(markers, dst)
    _, c = _config(paper_size)
    warped = cv2.warpPerspective(image, matrix, c["canvas"])
    projected = cv2.perspectiveTransform(markers.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    errors = np.linalg.norm(projected - dst, axis=1)
    if float(errors.max()) > MARKER_POSITION_TOLERANCE_PX:
        raise OMRScanError("Perspective correction error is too large.")
    return warped


def _validate_warp(warped, paper_size):
    _, c = _config(paper_size)
    expected = (c["canvas"][1], c["canvas"][0])
    if warped.shape[:2] != expected:
        raise OMRScanError("Invalid canonical page size.")

    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    scores = []
    for cx, cy in _marker_centers(paper_size):
        r = 35
        roi = gray[
            max(0, int(cy - r)):min(gray.shape[0], int(cy + r)),
            max(0, int(cx - r)):min(gray.shape[1], int(cx + r)),
        ]
        if roi.size == 0:
            raise OMRScanError("Registration marker region is missing.")
        darkness = 1 - float(np.mean(roi)) / 255
        scores.append(darkness)
        if darkness < 0.45:
            raise OMRScanError("A registration marker is not visible.")
    return round(float(np.mean(scores)) * 100, 2)


def _bubble_score(gray, cx, cy, paper_size):
    """Measure the bubble's inner area, excluding its printed outline."""
    _, c = _config(paper_size)
    r = c["sample_radius"]
    roi = gray[cy - r:cy + r + 1, cx - r:cx + r + 1]
    if roi.size == 0:
        return 0.0

    inner = max(5, int(r * 0.38))
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    mask = (xx * xx + yy * yy) <= inner * inner
    inner_pixels = roi[mask]
    darkness = 1.0 - float(np.percentile(inner_pixels, 35)) / 255.0
    return max(0.0, min(1.0, darkness))


def _read_question(gray, n, paper_size):
    scores = {
        choice: round(
            _bubble_score(gray, *bubble_center(n, choice, paper_size), paper_size), 4
        )
        for choice in CHOICES
    }
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top, top_score = ranked[0]
    _, second_score = ranked[1]
    marked = [choice for choice, score in ranked if score >= MIN_BUBBLE_SCORE]

    strong = [
        choice for choice, score in ranked
        if score >= MIN_BUBBLE_SCORE and score >= top_score * MULTIPLE_RELATIVE_SCORE
    ]

    if top_score < MIN_BUBBLE_SCORE:
        status, selected, confidence = "blank", None, 0
    elif len(strong) > 1:
        status, selected, confidence = "multiple", None, min(100, second_score * 100)
    elif top_score - second_score < AMBIGUITY_GAP:
        status, selected, confidence = "unclear", None, max(0, (top_score - second_score) * 100)
    else:
        status, selected, confidence = "detected", top, min(
            100, (top_score - second_score) * 100 + top_score * 50
        )

    return {
        "selected_choice": selected,
        "detected_choices": marked,
        "status": status,
        "confidence": round(confidence, 2),
        "darkness_scores": scores,
    }


def scan_answer_sheet(image_path, quiz, paper_size="A4"):
    key, c = _config(paper_size)
    if not Path(image_path).exists():
        raise OMRScanError("Uploaded image was not found.")

    image = cv2.imread(image_path)
    if image is None:
        raise OMRScanError("OpenCV could not decode the image.")

    questions = list(quiz.questions.all())
    if not questions:
        raise OMRScanError("This quiz has no questions.")
    if len(questions) > c["max_questions"]:
        raise OMRScanError(
            f"{key} answer sheet supports at most {c['max_questions']} questions."
        )

    markers = _select_four(_find_marker_candidates(image))
    warped = _warp(image, markers, key)
    geometry_confidence = _validate_warp(warped, key)
    gray = cv2.GaussianBlur(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (3, 3), 0)

    answers = []
    score = 0
    needs_review = False

    for question in questions:
        detected = _read_question(gray, question.number, key)
        status = detected["status"]
        selected = detected["selected_choice"]

        if status == "detected":
            status = "correct" if selected == question.correct_choice else "incorrect"
            correct = status == "correct"
            score += int(correct)
        else:
            correct = False
            needs_review = True

        answers.append({
            "question": question,
            "selected_choice": selected,
            "detected_choices": detected["detected_choices"],
            "is_correct": correct,
            "confidence": detected["confidence"],
            "status": status,
            "darkness_scores": detected["darkness_scores"],
        })

    total = len(answers)
    percentage = round(score / total * 100, 2) if total else 0
    return {
        "answers": answers,
        "score": score,
        "total_items": total,
        "percentage": percentage,
        "needs_review": needs_review,
        "geometry_confidence": geometry_confidence,
        "message": (
            f"{key} scan completed. Some answers require teacher review."
            if needs_review
            else f"{key} scan completed successfully."
        ),
        "paper_size": key,
    }
