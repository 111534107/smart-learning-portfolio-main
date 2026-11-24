"""B27：上傳佐證後說清楚放到哪、「我的檔案」總覽、小助手找檔案直接指路。資料僅為測試資料。"""
import io

from app.extensions import db
from app.models import Portfolio, User
from app.services.assistant_agent_service import is_file_question, navigation_links
from tests.test_cloud_storage_routes import FakeDriveClient, login, make_app, png_bytes, upload_transcript


def make_portfolio(app, username="student_syn", title="合成經歷"):
    with app.app_context():
        student = User.query.filter_by(username=username).one()
        portfolio = Portfolio(student_id=student.id, title=title, category="activity")
        db.session.add(portfolio)
        db.session.commit()
        return portfolio.id


def post_evidence(client, portfolio_id, **extra):
    return client.post(f"/student/portfolio/{portfolio_id}/evidence",
                       data={"file": (io.BytesIO(png_bytes()), "photo.png"), **extra},
                       content_type="multipart/form-data")


def test_card_drop_stays_on_list_and_highlights_the_card(tmp_path):
    app = make_app(tmp_path)
    portfolio_id = make_portfolio(app)
    client = login(app)

    response = post_evidence(client, portfolio_id, return_to="list")

    assert response.status_code == 302
    assert f"/student/portfolio?added={portfolio_id}#record-{portfolio_id}" in response.headers["Location"]
    page = client.get(f"/student/portfolio?added={portfolio_id}").get_data(as_text=True)
    assert "已把「photo.png」加到「合成經歷」的佐證" in page
    assert f'is-just-added" id="record-{portfolio_id}"' in page


def test_edit_page_upload_jumps_to_evidence_section_with_message(tmp_path):
    app = make_app(tmp_path)
    portfolio_id = make_portfolio(app)
    client = login(app)

    response = post_evidence(client, portfolio_id)

    assert response.headers["Location"].endswith(f"/student/portfolio/{portfolio_id}/edit#evidence-title")
    page = client.get(f"/student/portfolio/{portfolio_id}/edit").get_data(as_text=True)
    assert "已把「photo.png」加到「合成經歷」的佐證" in page


def test_my_files_lists_documents_and_evidence_with_location(tmp_path):
    app = make_app(tmp_path)
    mine = make_portfolio(app)
    others = make_portfolio(app, "other_syn", "別人的經歷")
    client = login(app)
    upload_transcript(client)
    post_evidence(client, mine)
    post_evidence(login(app, "other_syn"), others)

    page = client.get("/student/files").get_data(as_text=True)

    assert "transcript.png" in page and "成績單" in page
    assert "photo.png" in page and "合成經歷" in page
    assert "別人的經歷" not in page
    assert "本系統的伺服器" in page
    assert "這筆經歷確認後才會放進備審" in page
    assert 'href="/student/files"' in page  # 「我的資料」分頁有「我的檔案」


def test_my_files_shows_drive_location(tmp_path):
    app = make_app(tmp_path, FakeDriveClient())
    portfolio_id = make_portfolio(app)
    client = login(app)
    post_evidence(client, portfolio_id)

    assert "學校的 Google 雲端硬碟" in client.get("/student/files").get_data(as_text=True)


def test_assistant_points_file_questions_to_my_files(tmp_path):
    app = make_app(tmp_path)
    client = login(app)
    assert is_file_question("我剛剛上傳的成績單在哪裡？")
    assert not is_file_question("畢業門檻要幾張證照？")
    with app.app_context():
        student = User.query.filter_by(username="student_syn").one()
        links = navigation_links(student, "我剛剛上傳的成績單在哪裡？")
    assert links[0] == {"label": "前往我的檔案", "url": "/student/files"}

    reply = client.post("/assistant/ask", data={"message": "我剛剛上傳的成績單在哪裡？"}).get_json()
    assert "我的資料 → 我的檔案" in reply["answer"]
    assert "重補修" not in reply["answer"]
