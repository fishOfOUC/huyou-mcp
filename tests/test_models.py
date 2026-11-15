"""数据模型归一化单测：用真实接口返回的字段结构做样本。"""

from __future__ import annotations

from huyou_mcp.models import Comment, Feed, comments_from_page, feeds_from_page

FEED_RAW = {
    "sourceFeed": {
        "feedId": "1497670320637805952",
        "userName": "青挽阿挽",
        "userId": "1460080728938322816",
        "content": "我们学校户籍科在哪里呀",
        "commentCount": 1,
        "repostCount": 0,
        "stpl": 4,
        "score": 1794715253021,
        "circle": {"circleId": "796893005792620800", "circleName": "中国政法大学"},
    }
}

FEED_WITH_PICS = {
    "feedId": "1497327536751969280",
    "userName": "sue126",
    "content": "秋冬火锅季",
    "isTopFeed": 1,
    "picFeed": {
        "pics": [
            {
                "tp": "https://x/s_mini/1.jpg",
                "bp": "https://x/s_big/1.jpg",
                "rp": "https://x/pic/1.jpg",
            }
        ]
    },
}

COMMENT_RAW = {
    "commentId": "1497670349180045312",
    "userName": "狐友AI助手",
    "userId": "1163976342233099136",
    "content": "户籍科在主楼一楼。",
    "timeId": 1794716831294,
    "likeCount": 3,
    "liked": False,
    "replyCount": 0,
}


def test_feed_from_list_wrapper():
    feeds, meta = feeds_from_page({"feedList": [FEED_RAW], "pageInfo": {"hasMore": True, "score": -1, "totalCount": 371692}})
    assert len(feeds) == 1
    feed = feeds[0]
    assert feed.feed_id == "1497670320637805952"
    assert feed.author == "青挽阿挽"
    assert feed.circle_name == "中国政法大学"
    assert feed.url == "https://hy.sns.sohu.com/?feedDetail=1497670320637805952"
    assert feed.comment_count == 1
    assert meta["has_more"] is True


def test_published_at_estimated_only_for_new_sort():
    feeds, _ = feeds_from_page({"feedList": [FEED_RAW]}, sort="new")
    assert feeds[0].published_at is not None
    assert feeds[0].published_at_source == "feed_score"
    assert feeds[0].published_at.startswith("2026-11-15")

    feeds_hot, _ = feeds_from_page({"feedList": [FEED_RAW]}, sort="hot")
    assert feeds_hot[0].published_at is None


def test_composite_score_is_not_mistaken_for_time():
    # 热门排序的 score 是复合打分，不能被当成时间戳
    raw = {"feedId": "1", "score": 4209283728946, "content": "x"}
    feed = Feed.from_api(raw, sort="new")
    assert feed.published_at is None


def test_pic_urls_prefer_original():
    feed = Feed.from_api(FEED_WITH_PICS)
    assert feed.pics == ["https://x/pic/1.jpg"]
    assert feed.is_top is True


def test_hot_recommend_container_is_flattened():
    raw = {"tpl": 29, "rcmdCircleHotFeedContainer": {"feedList": [FEED_WITH_PICS]}}
    feeds, _ = feeds_from_page({"feedList": [raw]})
    assert len(feeds) == 1
    assert feeds[0].feed_id == "1497327536751969280"


def test_comment_model():
    comments, meta = comments_from_page({"list": [COMMENT_RAW], "pageInfo": {"hasMore": False}})
    assert len(comments) == 1
    comment = comments[0]
    assert comment.comment_id == "1497670349180045312"
    assert comment.like_count == 3
    assert comment.is_ai is True
    assert comment.created_at is not None
    assert meta["has_more"] is False


COMMENT_WITH_REPLIES = {
    "commentId": "1497651188152337664",
    "userName": "diwkcusina",
    "content": "如果选了好几种不同价格的海鲜，是付一份加工费还是好几份加工费呀",
    "timeId": 1794693062000,
    "likeCount": 0,
    "replyCount": 3,
    "sourceRegion": "山东",
    "replies": {
        "list": [
            {
                "commentId": "1497652000000000001",
                "userName": "不想说话盒盒",
                "content": "一份",
                "timeId": 1794693200000,
                "replyUserName": "diwkcusina",
                "replyCount": 0,
            }
        ],
        "hasMore": False,
    },
}


def test_comment_nested_replies_and_region():
    comments, _ = comments_from_page({"list": [COMMENT_WITH_REPLIES]})
    comment = comments[0]
    assert comment.region == "山东"
    assert comment.reply_count == 3
    assert len(comment.replies) == 1
    reply = comment.replies[0]
    assert reply.author == "不想说话盒盒"
    assert reply.reply_to == "diwkcusina"
    assert reply.text == "一份"
    # 转成 dict 后也要能带上回复，MCP 里直接给模型看
    assert comment.to_dict()["replies"][0]["reply_to"] == "diwkcusina"
