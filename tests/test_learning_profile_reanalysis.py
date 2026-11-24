import copy
import io
import json
import re
from pathlib import Path

import pytest
from PIL import Image

from app.extensions import db
from app.models import CredentialRecord, DocumentExtraction, LearningCourseRecord, SourceDocument
from test_learning_profile_confirmation import learning_profile_app, login


@pytest.fixture
def reviewed_document(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    app.config["DOCUMENT_ANALYSIS_PROVIDER"] = "fake"
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        Path(document.file_path).write_bytes(b"synthetic source")
        document.status = document.extraction.status = "confirmed"
        document.extraction.result_json = {"courses": [{"course_name": "Old", "credits": 2, "score": 80}]}
        document.extraction.confirmed_by_id = document.owner_id
        db.session.add(LearningCourseRecord(student_id=document.owner_id, source_document_id=document.id,
                                          course_name="Reviewed", normalized_course_name="Reviewed", credits=2, score=81))
        db.session.add(CredentialRecord(student_id=document.owner_id, source_document_id=document.id,
                                       credential_name="Reviewed credential"))
        db.session.commit()
    client = app.test_client()
    login(client)
    return app, client, document_id


def result():
    return {"courses": [{"course_name": "New", "credits": 0, "score": 0, "semester": None,
                          "grade_level": "5年級", "score_band": "不及格", "source_page": 1,
                          "source_line": 2, "source_bbox": [0, 0, 10, 20], "source_rotation": 90,
                          "field_confidence": {"course_name": 0.92, "credits": 0.4, "score": None,
                                               "semester": None, "grade_level": 0.8},
                          "needs_confirmation": True, "review_reasons": ["Check source"]}],
            "credentials": [], "source": {"engine": "synthetic-ocr"}, "warnings": ["Review all fields"]}


def test_reanalysis_creates_versioned_draft_preserving_confirmed_records(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    response = client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    assert response.status_code == 302
    with app.app_context():
        document = db.session.get(SourceDocument, doc_id)
        assert document.status == document.extraction.status == "extracted"
        assert document.extraction.confirmed_by_id is None
        assert document.extraction.result_json["draft_revision"]
        assert document.extraction.result_json["history"][-1]["result"]["courses"][0]["course_name"] == "Old"
        assert LearningCourseRecord.query.one().course_name == "Reviewed"
        assert CredentialRecord.query.one().credential_name == "Reviewed credential"
        assert DocumentExtraction.query.count() == 1
    page = client.get(response.location).get_data(as_text=True)
    assert 'name="draft_revision"' in page


def test_reanalysis_failure_preserves_exact_prior_extraction(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    with app.app_context():
        before = copy.deepcopy(DocumentExtraction.query.one().result_json)
    def fail(*_):
        raise RuntimeError("unavailable")
    monkeypatch.setattr("app.routes.student.analyze_document", fail)
    response = client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    assert response.status_code == 503
    page = response.get_data(as_text=True)
    assert 'name="course_0_course_name" value="Old"' in page
    assert 'data-review-grade="unknown"' in page
    with app.app_context():
        extraction = DocumentExtraction.query.one()
        assert extraction.result_json == before
        assert extraction.status == "confirmed"
        assert extraction.confirmed_by_id is not None
        assert db.session.get(SourceDocument, doc_id).status == "confirmed"
        assert LearningCourseRecord.query.one().score == 81
        assert CredentialRecord.query.count() == 1


def test_reanalysis_history_is_bounded_and_not_recursive(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    revisions = set()
    for _ in range(9):
        assert client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze").status_code == 302
        with app.app_context():
            payload = DocumentExtraction.query.one().result_json
            revisions.add(payload["draft_revision"])
            assert len(payload["history"]) <= 5
            assert all("history" not in item["result"] for item in payload["history"])
    assert len(revisions) == 9


@pytest.mark.parametrize("token", [None, "stale"])
def test_versioned_confirmation_rejects_missing_or_stale_token(reviewed_document, monkeypatch, token):
    app, client, doc_id = reviewed_document
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    data = {"courses_json": "[]", "credentials_json": "[]"}
    if token is not None:
        data["draft_revision"] = token
    assert client.post(f"/student/learning-profile/documents/{doc_id}/review/confirm", data=data).status_code == 409
    with app.app_context():
        assert LearningCourseRecord.query.one().course_name == "Reviewed"
        assert CredentialRecord.query.count() == 1


def test_new_confirmation_replaces_records_only_with_current_revision(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    with app.app_context():
        revision = DocumentExtraction.query.one().result_json["draft_revision"]
    data = {"draft_revision": revision, "scores_unlocked": "1",
            "courses_json": json.dumps(result()["courses"]), "credentials_json": "[]"}
    assert client.post(f"/student/learning-profile/documents/{doc_id}/review/confirm", data=data).status_code == 302
    with app.app_context():
        course = LearningCourseRecord.query.one()
        assert (course.course_name, course.credits, course.score, course.grade_level) == ("New", 0, 0, "5年級")
        assert CredentialRecord.query.count() == 0
        assert DocumentExtraction.query.one().status == "confirmed"
    # A second tab must not overwrite the just-confirmed edits.
    assert client.post(f"/student/learning-profile/documents/{doc_id}/review/confirm", data=data).status_code == 409


@pytest.mark.parametrize("suffix,method", [("reanalyze", "post"), ("review", "get"), ("source", "get"),
                                          ("courses/0/source", "get")])
def test_source_and_reanalysis_are_owner_only(reviewed_document, suffix, method):
    app, _, doc_id = reviewed_document
    client = app.test_client()
    login(client, "other_student")
    assert getattr(client, method)(f"/student/learning-profile/documents/{doc_id}/{suffix}").status_code == 403


def test_review_exposes_every_row_editable_fields_confidence_and_source(reviewed_document):
    app, client, doc_id = reviewed_document
    payload = result()
    payload["courses"].append({"course_name": "Uncertain name", "score": None, "credits": None, "grade_level": None})
    with app.app_context():
        DocumentExtraction.query.one().result_json = payload
        db.session.commit()
    page = client.get(f"/student/learning-profile/documents/{doc_id}/review").get_data(as_text=True)
    for field in ("course_name", "credits", "score", "semester", "grade_level"):
        assert f'name="course_0_{field}"' in page
        assert f'name="course_1_{field}"' in page
    assert 'name="course_0_credits" value="0"' in page
    assert 'name="course_1_credits" value=""' in page
    assert "92%" in page and "40%" in page and "未知" in page
    unknown_score = re.search(r'<small id="confidence-0-score"[^>]*>(.*?)</small>', page).group(1)
    assert "未知" in unknown_score and "0%" not in unknown_score
    assert "OCR 信心" in page and "不代表正確率" in page
    assert "synthetic-ocr" in page and "Check source" in page and "Review all fields" in page
    assert f"/documents/{doc_id}/courses/0/source" in page
    assert "Uncertain name" in page
    assert f"/documents/{doc_id}/reanalyze" in page
    assert f"/documents/{doc_id}/reanalyze" in client.get("/student/learning-profile").get_data(as_text=True)


def test_review_groups_grades_and_sorts_scores_without_losing_source_indices(reviewed_document):
    app, client, doc_id = reviewed_document
    courses = [
        {"course_name": "八十分", "grade_level": "一年級", "semester": "第一學期", "score": 80, "credits": 2},
        {"course_name": "最高分", "grade_level": "1年級", "semester": "第二學期", "score": 99, "credits": 0,
         "source_page": 1, "source_bbox": [0, 0, 10, 20]},
        {"course_name": "不及格", "grade_level": "一年級", "semester": "第二學期", "score": 59, "credits": 2},
        {"course_name": "待確認", "grade_level": "一年級", "semester": None, "score": None, "credits": 1},
        {"course_name": "二年級課程", "grade_level": "二年級", "semester": "第一學期", "score": 90, "credits": 2},
        {"course_name": "及格邊界", "grade_level": "一年級", "semester": "第一學期", "score": 60, "credits": 2,
         "score_band": "不及格"},
        {"course_name": "未識別年級", "grade_level": None, "semester": None, "score": 0, "credits": 0},
    ]
    with app.app_context():
        DocumentExtraction.query.one().result_json = {"courses": courses}
        db.session.commit()
    page = client.get(f"/student/learning-profile/documents/{doc_id}/review").get_data(as_text=True)
    assert '<select id="review-grade-filter"' in page
    for label in ("一年級", "二年級", "三年級", "四年級", "五年級", "年級待確認"):
        assert label in page
    for semester in ("第一學期", "第二學期"):
        assert re.search(
            rf'<details class="course-review-semester" data-semester="{semester}" open>\s*'
            rf'<summary[^>]*>\s*<span[^>]*>{semester}（',
            page,
        )
    def row_indices(grade, semester, kind):
        body = re.search(
            rf'<tbody data-review-grade="{grade}" data-review-semester="{semester}" data-review-kind="{kind}">(.*?)</tbody>',
            page, re.S,
        )
        assert body is not None
        return [int(value) for value in re.findall(r'data-course-index="(\d+)"', body.group(1))]
    assert row_indices("1", "第一學期", "passed") == [0, 5]
    assert row_indices("1", "第二學期", "passed") == [1]
    assert row_indices("1", "第二學期", "failed") == [2]
    assert row_indices("1", "學期待確認", "pending") == [3]
    assert row_indices("2", "第一學期", "passed") == [4]
    assert row_indices("unknown", "學期待確認", "failed") == [6]
    passed_body = re.search(r'<tbody data-review-grade="1" data-review-semester="第一學期" data-review-kind="passed">(.*?)</tbody>', page, re.S).group(1)
    assert "不及格／待確認" not in passed_body
    assert 'name="course_1_credits" value="0"' in page
    assert f"/documents/{doc_id}/courses/1/source" in page
    assert "最高成績" in page and "99 分" in page and "第二學期" in page
    assert "年级" not in page and "学期" not in page and "成绩" not in page


def test_crop_uses_saved_coordinates_rotation_and_clamps(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    # A red patch maps to x=0..10, y=10..20 after a PIL 90-degree CCW rotation.
    page = Image.new("RGB", (20, 30), "white")
    page.paste("red", (0, 0, 10, 10))
    payload = result()
    payload["courses"][0]["source_bbox"] = [-5, 10, 10, 25]
    with app.app_context():
        DocumentExtraction.query.one().result_json = payload
        db.session.commit()
    monkeypatch.setattr("app.services.ocr_pipeline.load_document_pages", lambda _: iter([page]))
    response = client.get(f"/student/learning-profile/documents/{doc_id}/courses/0/source?file_path=ignored&bbox=0,0,1,1")
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    with Image.open(io.BytesIO(response.data)) as crop:
        assert crop.size == (10, 10)
        assert crop.getpixel((5, 5)) == (255, 0, 0)


@pytest.mark.parametrize("changes", [{"source_page": 0}, {"source_page": "1"}, {"source_bbox": [20, 0, 10, 1]},
                                     {"source_bbox": [0, 0, float("nan"), 20]}, {"source_rotation": "bad"}])
def test_crop_rejects_invalid_saved_coordinates(reviewed_document, monkeypatch, changes):
    app, client, doc_id = reviewed_document
    payload = result()
    payload["courses"][0].update(changes)
    with app.app_context():
        DocumentExtraction.query.one().result_json = payload
        db.session.commit()
    monkeypatch.setattr("app.services.ocr_pipeline.load_document_pages", lambda _: iter([Image.new("RGB", (20, 30))]))
    assert client.get(f"/student/learning-profile/documents/{doc_id}/courses/0/source").status_code == 400


def test_original_download_uses_owned_saved_file(reviewed_document):
    _, client, doc_id = reviewed_document
    response = client.get(f"/student/learning-profile/documents/{doc_id}/source?path=ignored")
    assert response.status_code == 200
    assert response.data == b"synthetic source"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "no-store" in response.headers["Cache-Control"]


def test_actual_previous_draft_cannot_confirm_after_second_analysis(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    with app.app_context():
        old_token = DocumentExtraction.query.one().result_json["draft_revision"]
    client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    assert client.post(f"/student/learning-profile/documents/{doc_id}/review/confirm", data={
        "draft_revision": old_token, "courses_json": json.dumps(result()["courses"]), "credentials_json": "[]",
    }).status_code == 409
    assert client.get(f"/student/learning-profile/documents/{doc_id}/courses/0/source?revision={old_token}").status_code == 409
    with app.app_context():
        assert LearningCourseRecord.query.one().course_name == "Reviewed"
        assert CredentialRecord.query.count() == 1


@pytest.mark.parametrize("course", [{"course_name": None}, {"course_name": "New", "score": 101},
                                    {"course_name": "New", "credits": -1},
                                    {"course_name": "New", "score": 85.9},
                                    {"course_name": "New", "score": True},
                                    {"course_name": "New", "grade_level": "6年級"}])
def test_invalid_confirmation_rolls_back_prior_records_and_draft(reviewed_document, monkeypatch, course):
    app, client, doc_id = reviewed_document
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    with app.app_context():
        before = copy.deepcopy(DocumentExtraction.query.one().result_json)
    response = client.post(f"/student/learning-profile/documents/{doc_id}/review/confirm", data={
        "draft_revision": before["draft_revision"], "scores_unlocked": "1",
        "courses_json": json.dumps([course]), "credentials_json": "[]",
    })
    assert response.status_code == 400
    with app.app_context():
        assert DocumentExtraction.query.one().result_json == before
        assert LearningCourseRecord.query.one().course_name == "Reviewed"
        assert CredentialRecord.query.count() == 1


def test_versioned_incomplete_form_cannot_silently_erase_confirmed_data(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze")
    with app.app_context():
        revision = DocumentExtraction.query.one().result_json["draft_revision"]
    assert client.post(f"/student/learning-profile/documents/{doc_id}/review/confirm", data={"draft_revision": revision}).status_code == 400
    with app.app_context():
        assert LearningCourseRecord.query.count() == CredentialRecord.query.count() == 1


def test_crop_reads_real_saved_image(reviewed_document, tmp_path):
    app, client, doc_id = reviewed_document
    image_path = tmp_path / "synthetic.png"
    with Image.new("RGB", (20, 30), "blue") as image:
        image.save(image_path)
    with app.app_context():
        document = db.session.get(SourceDocument, doc_id)
        document.file_path = str(image_path)
        document.extraction.result_json = result()
        db.session.commit()
    response = client.get(f"/student/learning-profile/documents/{doc_id}/courses/0/source")
    assert response.status_code == 200
    with Image.open(io.BytesIO(response.data)) as crop:
        assert crop.size == (10, 20)
        assert crop.getpixel((5, 5)) == (0, 0, 255)


def test_unreadable_crop_is_controlled_error(reviewed_document):
    app, client, doc_id = reviewed_document
    with app.app_context():
        DocumentExtraction.query.one().result_json = result()
        db.session.commit()
    assert client.get(f"/student/learning-profile/documents/{doc_id}/courses/0/source").status_code == 503


def test_reanalysis_of_failed_extraction_can_recover(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    with app.app_context():
        document = db.session.get(SourceDocument, doc_id)
        document.status = "analysis_failed"
        document.extraction.status = "failed"
        document.extraction.result_json = None
        document.extraction.error_message = "prior failure"
        db.session.commit()
    monkeypatch.setattr("app.routes.student.analyze_document", lambda *_: result())
    assert client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze").status_code == 302
    with app.app_context():
        extraction = DocumentExtraction.query.one()
        assert extraction.error_message is None
        assert extraction.status == "extracted"
        assert extraction.result_json["courses"][0]["course_name"] == "New"


def test_reanalysis_passes_owned_saved_source_and_configured_provider(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    app.config["DOCUMENT_ANALYSIS_PROVIDER"] = "ocr"
    with app.app_context():
        saved_path = Path(db.session.get(SourceDocument, doc_id).file_path)
    def analyze(document_type, path, provider):
        if document_type == "transcript" and path == saved_path and provider == "ocr":
            return result()
        raise RuntimeError("wrong source")
    monkeypatch.setattr("app.routes.student.analyze_document", analyze)
    assert client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze", data={"file_path": "ignored"}).status_code == 302
    with app.app_context():
        assert DocumentExtraction.query.one().provider == "ocr"
        assert DocumentExtraction.query.one().result_json["courses"][0]["credits"] == 0


def test_reanalysis_does_not_overwrite_a_concurrently_changed_draft(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    def analyze(*_):
        with app.app_context():
            extraction = DocumentExtraction.query.one()
            extraction.result_json = {**result(), "draft_revision": "concurrent-winner"}
            db.session.commit()
        return result()
    monkeypatch.setattr("app.routes.student.analyze_document", analyze)
    assert client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze").status_code == 409
    with app.app_context():
        assert DocumentExtraction.query.one().result_json["draft_revision"] == "concurrent-winner"
        assert LearningCourseRecord.query.one().course_name == "Reviewed"
        assert CredentialRecord.query.count() == 1


def test_reanalysis_checks_start_revision_even_if_timestamp_is_unchanged(reviewed_document, monkeypatch):
    app, client, doc_id = reviewed_document
    with app.app_context():
        DocumentExtraction.query.one().result_json = {**result(), "draft_revision": "start-revision"}
        db.session.commit()
    def analyze(*_):
        with app.app_context():
            extraction = DocumentExtraction.query.one()
            # Simulate a competing writer retaining timestamp precision/value.
            DocumentExtraction.query.filter_by(id=extraction.id).update({
                "result_json": {**result(), "draft_revision": "concurrent-winner"},
                "updated_at": extraction.updated_at,
            })
            db.session.commit()
        return result()
    monkeypatch.setattr("app.routes.student.analyze_document", analyze)
    assert client.post(f"/student/learning-profile/documents/{doc_id}/reanalyze").status_code == 409
    with app.app_context():
        assert DocumentExtraction.query.one().result_json["draft_revision"] == "concurrent-winner"
        assert LearningCourseRecord.query.one().course_name == "Reviewed"


def test_confirmation_detects_revision_change_during_request(reviewed_document, monkeypatch):
    from app.routes import student

    app, client, doc_id = reviewed_document
    with app.app_context():
        DocumentExtraction.query.one().result_json = {**result(), "draft_revision": "opened-revision"}
        db.session.commit()
    original_load = student._load_record_list
    def load(raw_value, field_name):
        if field_name == "courses_json":
            with app.app_context():
                extraction = DocumentExtraction.query.one()
                extraction.result_json = {**result(), "draft_revision": "concurrent-winner"}
                db.session.commit()
        return original_load(raw_value, field_name)
    monkeypatch.setattr(student, "_load_record_list", load)
    assert client.post(f"/student/learning-profile/documents/{doc_id}/review/confirm", data={
        "draft_revision": "opened-revision", "courses_json": "[]", "credentials_json": "[]",
    }).status_code == 409
    with app.app_context():
        assert DocumentExtraction.query.one().result_json["draft_revision"] == "concurrent-winner"
        assert LearningCourseRecord.query.one().course_name == "Reviewed"
        assert CredentialRecord.query.count() == 1
