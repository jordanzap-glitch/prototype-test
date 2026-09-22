# OMR automated tests

Install test dependencies:

    python -m pip install pytest pytest-django

Run:

    python -m pytest tests/test_omr.py -q

The suite synthesizes A4 pages and tests marker detection, perspective correction, cropped pages, glare, blur, blank answers, multiple marks, and 50-item grading. Real JPG/PNG camera samples may be placed in tests/sample_scans/.

The tests prefer review/rejection over silently assigning a grade to degraded scans.
