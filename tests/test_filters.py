"""筛选规则单测：用海大圈真实帖子当样本，确保「有用信息」进、噪音出。"""

from __future__ import annotations

import pytest

from huyou_mcp.filters import classify

USEFUL_SAMPLES = [
    "校园跑步怎么更省事啊，有没有什么技巧，每次都跑不完",
    "求推荐，哪个老师的数据库比较好过，给分高不高",
    "管理学院大一期中考试原题，有需要的自取",
    "四六级报名什么时候截止，教务系统里没找到通知",
    "校医院周末可以拍片吗？上次去说只有工作日",
    "一卡通丢了在哪补办，需要带什么材料",
    "宿舍空调报修怎么弄，师傅大概多久能来",
    "二手出一个宿舍挂篮，能放电脑，15 块",
    "图书馆四楼自习室几点开门，期末会不会满",
    "有没有羽毛球搭子，体育馆场地怎么预约",
]

NOISE_SAMPLES = [
    # 骂人
    "哪个傻逼往我书包里塞东西，你妈保胎针打你屁眼里了是吧",
    # 纯抱怨
    "崩溃了，受不了了，这日子没法过了啊啊啊啊啊",
    # 情感交友
    "有没有单身的可以认识一下，想找个女朋友",
    # 打探钱
    "大家一个月生活费多少啊，家里给我 2000 够吗",
    # 八卦
    "听说教务处那个事有黑料，谁有瓜",
    # 广告
    "加微信领优惠券，扫码进群，抽奖送双人煲",
    # 纯水
    "听海已沦陷",
]


@pytest.mark.parametrize("text", USEFUL_SAMPLES)
def test_useful_posts_pass(text: str):
    verdict = classify(text, comment_count=3)
    assert verdict.useful, f"应判为有用：{text} → {verdict.reason}"


@pytest.mark.parametrize("text", NOISE_SAMPLES)
def test_noise_posts_are_filtered(text: str):
    verdict = classify(text, comment_count=3)
    assert not verdict.useful, f"应被判为噪音：{text} → {verdict.reason}"


def test_profanity_beats_useful_keyword():
    # 既提到食堂又在骂人 → 不推
    verdict = classify("食堂那个傻逼阿姨又给我打凉菜，他妈的", comment_count=5)
    assert not verdict.useful
    assert "脏话" in verdict.noise_hits


def test_extra_keywords_from_config():
    assert not classify("求带看世界杯", comment_count=0).useful
    assert classify("求带看世界杯", comment_count=0, extra_useful=["世界杯"]).useful
    assert not classify("校园跑求带，一起跑", comment_count=0, extra_noise=["求带"]).useful


def test_short_post_without_topic_is_dropped():
    assert not classify("啊啊啊啊", comment_count=0).useful
