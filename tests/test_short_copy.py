"""公開首頁與小助手要「一兩句短話」：文字太長就失敗。"""
import re

from app import create_app
from app.content.five_year_plan import FIVE_YEAR_PLAN, NEXT_STOPS

MAX_LINE = 30


def test_five_year_plan_lines_are_short():
    for stop in FIVE_YEAR_PLAN:
        assert len(stop["summary"]) <= MAX_LINE, stop
        assert len(stop["keep"]) <= 3
    for stop in NEXT_STOPS:
        assert len(stop["text"]) <= MAX_LINE, stop


def test_landing_page_paragraphs_are_short():
    html = create_app({"TESTING": True}).test_client().get("/").get_data(as_text=True)
    for tag in ("cover__lead", "chapter__lead"):
        for text in re.findall(rf'class="{tag}">(.*?)</p>', html, re.S):
            assert len(text.strip()) <= MAX_LINE * 2, text
    body = re.sub(r"<(script|style)[\s\S]*?</\1>|<[^>]+>", "", html)
    assert len(re.sub(r"\s+", "", body)) < 1400


def test_story_scenes_keep_one_short_heading_and_one_short_sentence():
    html = create_app({"TESTING": True}).test_client().get("/").get_data(as_text=True)
    scenes = re.findall(r'<section[^>]+data-story-step="\d"[\s\S]*?</section>', html)

    assert len(scenes) == 6
    for scene in scenes:
        assert len(re.findall(r"<h[12][^>]*>[\s\S]*?</h[12]>", scene)) == 1
        leads = re.findall(r'class="story-scene__lead"[^>]*>(.*?)</p>', scene, re.S)
        assert len(leads) == 1
        plain_lead = re.sub(r"<[^>]+>|\s+", "", leads[0])
        assert len(plain_lead) <= MAX_LINE, plain_lead

    # 規格另要求五年各一句、三個下一站沿用集中內容；除此之外不增加故事段落。
    extra_paragraphs = re.findall(
        r'<(?:li class="stop"|div class="ticket__body")[^>]*>[\s\S]*?<p>(.*?)</p>',
        "".join(scenes),
    )
    assert len(extra_paragraphs) == len(FIVE_YEAR_PLAN) + len(NEXT_STOPS)
    assert all(len(re.sub(r"<[^>]+>|\s+", "", text)) <= MAX_LINE for text in extra_paragraphs)
    all_paragraphs = re.findall(r"<p(?:\s[^>]*)?>(.*?)</p>", "".join(scenes), re.S)
    assert len(all_paragraphs) == 6 + len(extra_paragraphs) + 6  # 每幕眉題、主句，加上八張內容卡
