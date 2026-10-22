"""不及格課程自動配對之後的重補修：標示何時、哪一學期、幾分重修及格（合成資料）。"""
from app.services.course_review_presentation import prepare_course_review_rows


def course(name, grade, semester, score, makeup=None, credits=3):
    return {"course_name": name, "grade_level": grade, "semester": semester, "score": score,
            "credits": credits, "makeup_season": makeup}


def test_failed_course_links_to_later_summer_makeup():
    rows = prepare_course_review_rows([
        course("模擬程式語言", "3年級", "第一學期", 91),
        course("模擬程式語言", "3年級", "第二學期", 58),
        course("模擬程式語言", "3年級", "第二學期", 85, makeup="summer"),
    ])

    retake = rows[1]["retake"]
    assert retake["index"] == 2
    assert retake["label"] == "3年級 暑修 85 分"
    assert rows[2]["retake_of"]["label"] == "3年級第二學期 58 分"
    assert "retake" not in rows[0]   # 及格的課不需要


def test_earlier_passing_attempt_is_not_a_retake():
    rows = prepare_course_review_rows([
        course("模擬程式語言", "3年級", "第一學期", 91),
        course("模擬程式語言", "3年級", "第二學期", 58),
    ])

    assert rows[1].get("retake") is None


def test_failed_course_links_to_later_regular_semester_retake():
    rows = prepare_course_review_rows([
        course("模擬 統計學", "2年級", "第一學期", 50),
        course("模擬統計學", "3年級", "第一學期", 72),
    ])

    assert rows[0]["retake"]["label"] == "3年級第一學期 72 分"


def test_winter_makeup_comes_between_first_and_second_semester():
    rows = prepare_course_review_rows([
        course("模擬會計學", "1年級", "第一學期", 40),
        course("模擬會計學", "1年級", "第一學期", 66, makeup="winter"),
    ])

    assert rows[0]["retake"]["label"] == "1年級 寒修 66 分"


def test_failed_retake_does_not_count_and_the_next_pass_is_used():
    rows = prepare_course_review_rows([
        course("模擬微積分", "1年級", "第二學期", 45),
        course("模擬微積分", "1年級", "第二學期", 52, makeup="summer"),
        course("模擬微積分", "2年級", "第一學期", 70),
    ])

    assert rows[0]["retake"]["label"] == "2年級第一學期 70 分"


def test_review_page_shows_retake_note_on_failed_course(tmp_path):
    from app import create_app
    from app.extensions import db
    from app.models import DocumentExtraction, SourceDocument, User

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        student = User(username="student_syn", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        document = SourceDocument(owner_id=student.id, document_type="transcript", display_name="合成成績單.png",
                                  file_path=str(tmp_path / "none.png"), sha256="0" * 64, status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(source_document_id=document.id, provider="rapidocr", status="extracted",
                                          result_json={"draft_revision": "r1", "courses": [
            course("模擬程式語言", "3年級", "第二學期", 58),
            course("模擬程式語言", "3年級", "第二學期", 85, makeup="summer"),
        ]}))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "student_syn", "password": "pw"})

    html = client.get("/student/learning-profile/documents/1/review").get_data(as_text=True)

    assert "已重補修：3年級 暑修 85 分（及格）" in html
    assert "重補修：補 3年級第二學期 58 分" in html
