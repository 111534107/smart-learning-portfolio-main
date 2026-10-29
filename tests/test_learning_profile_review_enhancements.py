import re

from app import create_app
from app.extensions import db
from app.models import DocumentExtraction, LearningCourseRecord, SourceDocument, User
from app.services.course_review_presentation import (
    build_course_review_groups,
    prepare_course_review_rows,
    traditionalize_course_name,
)


def test_course_names_are_converted_to_taiwan_traditional_without_touching_raw_text():
    source_text = "资讯科技\n程式设计"
    converted = [traditionalize_course_name(value) for value in source_text.splitlines()]
    assert converted == ["資訊科技", "程式設計"]
    assert source_text == "资讯科技\n程式设计"


def test_groups_keep_makeup_season_and_include_top_three_scored_rows():
    courses = [
        {"course_name": "暑期補修", "grade_level": "一年級", "semester": "第二學期",
         "score": 58, "school_year": 114, "makeup_season": "summer"},
        {"course_name": "高分課程", "grade_level": "一年級", "semester": "第一學期",
         "score": 99, "school_year": 113},
        {"course_name": "寒期補修", "grade_level": "一年級", "semester": "第一學期",
         "score": 65, "school_year": 114, "makeup_season": "winter"},
        {"course_name": "第四名", "grade_level": "一年級", "semester": "第二學期", "score": 70},
    ]
    group = build_course_review_groups(courses)[0]
    assert [entry["course"]["course_name"] for entry in group["top_three"]] == [
        "高分課程", "第四名", "寒期補修",
    ]
    assert group["top_three"][0]["school_year"] == 113
    assert group["top_three"][2]["makeup_season"] == "winter"


def test_groups_separate_semesters_and_sort_scores_within_each():
    courses = [
        {"course_name": "二學期低分", "grade_level": "一年級", "semester": "第二學期", "score": 72},
        {"course_name": "一學期低分", "grade_level": "一年級", "semester": "第一學期", "score": 65},
        {"course_name": "二學期高分", "grade_level": "一年級", "semester": "第二學期", "score": 95},
        {"course_name": "一學期高分", "grade_level": "一年級", "semester": "第一學期", "score": 88},
        {"course_name": "二學期不及格", "grade_level": "一年級", "semester": "第二學期", "score": 50},
        {"course_name": "學期不明", "grade_level": "一年級", "semester": None, "score": None},
    ]
    semesters = build_course_review_groups(courses)[0]["semesters"]
    assert [semester["label"] for semester in semesters] == ["第一學期", "第二學期", "學期待確認"]
    assert [[entry["index"] for entry in semester["passed"]] for semester in semesters] == [
        [3, 1], [2, 0], [],
    ]
    assert [entry["index"] for entry in semesters[1]["failed"]] == [4]
    assert [entry["index"] for entry in semesters[2]["pending"]] == [5]


def test_pending_review_rows_exclude_page_wide_layout_warnings_but_include_field_issues():
    rows = prepare_course_review_rows([
        {"course_name": "完整課程", "credits": 3, "score": 81,
         "semester": "第一學期", "grade_level": "一年級", "needs_confirmation": True,
         "review_reasons": ["學期依表格位置推定，請核對表頭。"],
         "field_confidence": {"course_name": 0.95, "credits": 1, "score": 1}},
        {"course_name": "低信心課名", "credits": 3, "score": 81,
         "semester": "第一學期", "grade_level": "一年級",
         "field_confidence": {"course_name": 0.74, "credits": 1, "score": 1}},
        {"course_name": "普通課程", "credits": 2, "score": 88,
         "semester": "第一學期", "grade_level": "一年級",
         "needs_confirmation": True,
         "review_reasons": ["學期依表格位置推定，請核對表頭。"],
         "field_confidence": {"course_name": 0.95, "credits": 1, "score": 1}},
        {"course_name": "課名待確認", "credits": 2, "score": 88,
         "semester": "第一學期", "grade_level": "一年級"},
        {"course_name": "缺學分", "credits": None, "score": 88,
         "semester": "第一學期", "grade_level": "一年級"},
        {"course_name": "學分文字待確認", "credits": "待確認", "score": 88,
         "semester": "第一學期", "grade_level": "一年級"},
    ])
    assert [row["needs_review"] for row in rows] == [False, True, False, True, True, True]


def _review_app(tmp_path, courses):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        user = User(username="review_student", display_name="Review Student", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        document = SourceDocument(
            owner_id=user.id, document_type="transcript", display_name="成績單.jpg",
            file_path=str(tmp_path / "transcript.jpg"), sha256="a" * 64, status="extracted",
        )
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(
            source_document_id=document.id, provider="test", status="extracted",
            result_json={"courses": courses, "raw_text": "资讯科技 2 88"},
        ))
        db.session.commit()
        document_id = document.id
    client = app.test_client()
    client.post("/login", data={"username": "review_student", "password": "pw"})
    return app, client, document_id


def test_review_page_has_combined_filters_visible_pending_badges_and_default_locked_scores(tmp_path):
    app, client, document_id = _review_app(tmp_path, [
        {"course_name": "资讯科技", "credits": 2, "score": 88, "semester": "第一學期",
         "grade_level": "一年級", "school_year": 114, "makeup_season": "summer"},
        {"course_name": "課名待確認", "credits": None, "score": None,
         "semester": None, "grade_level": "一年級", "needs_confirmation": True},
    ])
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert "資訊科技" in page and "资讯科技" in page
    assert 'id="review-failure-filter"' in page
    assert '<option value="pending">只看缺學分</option>' in page
    assert "只列出學分空白或待確認的課程" in page
    assert 'id="review-makeup-filter"' in page
    assert re.search(r'<button[^>]*id="lock-all-scores"[^>]*>.*?解鎖成績', page, re.S)
    assert 'id="all-fields-locked" name="all_fields_locked" value="0"' in page
    assert 'data-makeup-season="summer"' in page
    assert 'data-needs-review="true"' in page
    assert "⚠ 待確認" in page
    assert 'id="course-0-score"' in page and 'readonly' in page
    assert '<th scope="col">成績</th>' in page
    assert 'class="score-unlock toggle-score-lock"' not in page
    assert 'id="toggle-score-lock"' not in page
    assert "全部展開" not in page
    assert re.search(r'<details[^>]*class="score-group course-year-group"[^>]*open', page)
    assert "收合時最高三筆" in page


def test_confirmation_preserves_locked_scores_and_saves_makeup_season(tmp_path):
    app, client, document_id = _review_app(tmp_path, [
        {"course_name": "資訊科技", "credits": 2, "score": 88, "semester": "第一學期",
         "grade_level": "一年級", "school_year": 114, "makeup_season": "summer"},
    ])
    response = client.post(
        f"/student/learning-profile/documents/{document_id}/review/confirm",
        data={
            "course_input_mode": "fields",
            "course_0_course_name": "资讯科技",
            "course_0_credits": "2",
            "course_0_score": "12",
            "course_0_semester": "第一學期",
            "course_0_grade_level": "一年級",
            "draft_revision": "",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        course = LearningCourseRecord.query.one()
        assert (course.score, course.course_name) == (88, "資訊科技")
        assert course.makeup_season == "summer"
        assert DocumentExtraction.query.one().result_json["raw_text"] == "资讯科技 2 88"


def test_unlocked_confirmation_can_edit_score_and_preserves_winter_season(tmp_path):
    app, client, document_id = _review_app(tmp_path, [
        {"course_name": "資料處理", "credits": 3, "score": 55, "semester": "第二學期",
         "grade_level": "二年級", "school_year": 115, "makeup_season": "winter"},
    ])
    response = client.post(
        f"/student/learning-profile/documents/{document_id}/review/confirm",
        data={
            "course_input_mode": "fields", "scores_unlocked": "1",
            "course_0_course_name": "資料處理", "course_0_credits": "3",
            "course_0_score": "75", "course_0_semester": "第二學期",
            "course_0_grade_level": "二年級",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        course = LearningCourseRecord.query.one()
        assert (course.score, course.makeup_season) == (75, "winter")


def test_all_fields_locked_confirmation_preserves_original_course_fields(tmp_path):
    app, client, document_id = _review_app(tmp_path, [
        {"course_name": "原始課名", "credits": 3, "score": 85, "semester": "第二學期",
         "grade_level": "三年級", "school_year": 115, "makeup_season": "winter"},
    ])
    response = client.post(
        f"/student/learning-profile/documents/{document_id}/review/confirm",
        data={"course_input_mode": "fields", "all_fields_locked": "1", "scores_unlocked": "1",
              "course_0_course_name": "誤觸改動", "course_0_credits": "0", "course_0_score": "12",
              "course_0_semester": "第一學期", "course_0_grade_level": "一年級"},
    )
    assert response.status_code == 302
    with app.app_context():
        course = LearningCourseRecord.query.one()
        assert (course.course_name, course.credits, course.score, course.semester, course.grade_level) == (
            "原始課名", 3, 85, "第二學期", "三年級",
        )


def test_review_marks_low_confidence_rows(tmp_path):
    app, client, document_id = _review_app(tmp_path, [
        {"course_name": "資訊科技", "credits": 2, "score": 88, "semester": "第一學期",
         "grade_level": "一年級",
         "field_confidence": {"course_name": 0.95, "credits": 0.98, "score": 0.97}},
        {"course_name": "程式設計", "credits": 3, "score": 76, "semester": "第一學期",
         "grade_level": "一年級",
         "field_confidence": {"course_name": 0.95, "credits": 0.6, "score": 0.97}},
    ])
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert page.count('class="needs-review"') == 1
    assert "還有 1 列待確認" in page
    assert 'class="review-layout"' in page
    # 學期、年級沒有信心資料時不標橘色；只有低信心的學分欄標出
    assert 'field-low" data-label="第幾學期"' not in page
    assert 'field-low" data-label="年級"' not in page
    assert page.count('field-low" data-label="學分"') == 1


def test_review_unknown_confidence_is_not_orange(tmp_path):
    app, client, document_id = _review_app(tmp_path, [
        {"course_name": "資訊科技", "credits": 2, "score": 88, "semester": "第一學期",
         "grade_level": "一年級",
         "field_confidence": {"course_name": 0.95, "credits": 0.6}},
    ])
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    # 學分信心已知且偏低才標橘色；成績信心未知，只顯示「信心 未知」，不標橘色
    assert page.count('field-low" data-label="學分"') == 1
    assert 'field-low" data-label="成績"' not in page
    assert "信心 未知" in page
