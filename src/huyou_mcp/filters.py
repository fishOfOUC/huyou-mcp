"""帖子「有用 / 噪音」判定。

目标（用户定的口径）：
    只推送有实用信息的帖子，例如
        - 校园跑怎么更省事、体测技巧、哪门课老师好/不好、选课建议
        - 考试真题、复习资料、保研考研实习招聘、办事流程（校医院/户籍/报修/校园卡）
        - 食堂/外卖/快递/失物招领/二手之类的具体信息
    不推送：
        - 纯抱怨、情绪发泄、骂人
        - 与学习和校园生活无关的无意义提问（找女朋友、大家有多少钱…）
        - 商单/抽奖/拉群广告

这里是「规则初筛」，保证命令行/定时任务单独跑也能用；MCP 里再让模型做二次判断
（huyou_new_feeds 会带上规则给的 label 和命中词，模型可以推翻）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# (标签, 正则) —— 命中即说明这条帖子包含实用信息
USEFUL_TOPICS: list[tuple[str, str]] = [
    ("选课/老师", r"选课|课程|老师|教师|教授|讲师|给分|点名|挂科|水课|硬课|绩点|gpa|学分"),
    ("考试/复习", r"考试|期中|期末|真题|原题|题库|复习|考纲|重点|补考|缓考|四六级|雅思|托福|考研|保研|复试|笔试"),
    ("学业/教务", r"教务|学籍|转专业|双学位|辅修|交换|课程表|培养方案|学分认定|成绩单|毕业|论文|答辩|导师"),
    ("实习/就业", r"实习|招聘|内推|秋招|春招|校招|简历|面试|offer|兼职|家教|宣讲会"),
    ("办事流程", r"校医院|医保|报销|户籍|档案|居住证|身份证|校园卡|一卡通|门禁|报修|维修|电费|水费|网费|校园网|退宿|入住|宿舍调整|断电|停电|断网|没电|停水|热水"),
    ("校园跑/体育", r"校园跑|跑步|体测|800|1000|引体|体育课|免测|打卡|锻炼|游泳馆|体育馆|健身房|操场|篮球场|羽毛球|乒乓球|球场|场地|器械|预约"),
    ("吃喝生活", r"食堂|餐厅|外卖|好吃|难吃|推荐|性价比|优惠|折扣|套餐|超市|快递|菜鸟|驿站|洗衣|澡堂|浴室|空调|暖气|烤红薯|有卖|哪买|在哪买"),
    ("活动/社团/竞赛", r"社团|招新|讲座|分享会|比赛|竞赛|集创赛|大创|srdp|数模|建模|挑战赛|组队|队友|报名|志愿|活动|演出|展览|招聘会|宣讲"),
    ("学习资源", r"资料|笔记|课件|ppt|模板|网课|慕课|图书馆|自习室|自习|借书|文献|数据库|英语|编程|软件|工具|教材|真题"),
    ("科研/培养", r"科研|课题|实验室|培养方案|培养|技能|转专业|辅修|交换|选修|必修"),
    ("失物/二手", r"失物|捡到|丢了|丢失|拾到|闲置|二手|转卖|求购|代取|代跑|拼单|团购|收一个|收个|出一个|出个|出闲置|求借|借个|借用|租个|出租"),
    ("攻略/经验", r"攻略|教程|经验|流程|怎么办|怎么弄|如何|技巧|省事|省钱|避坑|注意事项|指南|求问|求助|请教"),
    ("通知/政策", r"通知|公告|政策|规定|新规|放假|开学|返校|报到|体检|开学典礼|校历"),
]

# 弱信号：只是「在提问 / 在打听」，单靠它不足以判定有用（+1 分，最多 +1）
WEAK_USEFUL: list[str] = [
    r"求问|求助|请教|问一下|想问|有人知道|有没有人知道|怎么弄|怎么办|怎么准备|需要准备|"
    r"有没有|哪里有|去哪|推荐一下",
]

# 命中即判定为噪音（强）
NOISE_TOPICS: list[tuple[str, str]] = [
    ("交友/情感", r"找对象|处对象|征友|交友|相亲|脱单|单身|恋爱|谈恋爱|女朋友|男朋友|找女|找男|对象吗|crush|表白|约起来|加个微信|认识一下"),
    ("钱/隐私打探", r"大家有多少钱|有多少存款|生活费多少|一个月生活费|家里给多少|收入多少|工资多少|存款|余额|借我点钱|借钱"),
    ("纯情绪发泄", r"崩溃了|受不了了|无语了|烦死了|气死|服了|吐了|emo了|活着没意思|想退学|骂人"),
    ("脏话", r"傻逼|煞笔|智障|弱智|狗东西|他妈的|你妈|妈的|操你|cnm|nmsl|sb|滚蛋|有病吧|贱人|死全家|垃圾人"),
    ("八卦", r"八卦|吃瓜|瓜田|黑料|撕逼|挂人|人肉|爆料"),
    ("广告/引流", r"抽奖|中奖|进群|扫码|加微信|加v|私信我|代购|微商|推广|招募代理|返现|优惠券|二维码|点关注|点赞|转发抽"),
    ("游戏代练/组队", r"代练|陪玩|上分|开黑|上号|带带我"),
]

# 强噪音：只要命中就不推，不看其他分数
HARD_NOISE_LABELS = {"脏话", "交友/情感", "钱/隐私打探", "广告/引流"}

_COMPILED_USEFUL = [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in USEFUL_TOPICS]
_COMPILED_NOISE = [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in NOISE_TOPICS]
_COMPILED_WEAK = re.compile("|".join(WEAK_USEFUL), re.IGNORECASE)

# 短于这个长度、又没有命中任何有用主题，基本是「哦」「啊啊啊」这种灌水
MIN_MEANINGFUL_LEN = 8


@dataclass
class Verdict:
    useful: bool
    score: int
    useful_hits: list[str] = field(default_factory=list)
    noise_hits: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def reason(self) -> str:
        if self.useful:
            return f"命中实用主题：{'、'.join(self.useful_hits)}"
        if self.noise_hits:
            return f"噪音（{'、'.join(self.noise_hits)}）"
        return self.note or "没有实用信息"

    def to_dict(self) -> dict[str, object]:
        return {
            "useful": self.useful,
            "score": self.score,
            "useful_hits": self.useful_hits,
            "noise_hits": self.noise_hits,
            "reason": self.reason,
        }


def classify(
    text: str,
    *,
    comment_count: int = 0,
    min_score: int = 2,
    extra_useful: "list[str] | tuple[str, ...]" = (),
    extra_noise: "list[str] | tuple[str, ...]" = (),
) -> Verdict:
    """给一条帖子的正文打分，判定是否值得推送到邮箱。

    extra_useful / extra_noise 来自 config.toml，按普通子串匹配（不分大小写）。
    """
    body = (text or "").strip()
    useful_hits: list[str] = []
    noise_hits: list[str] = []

    for label, pattern in _COMPILED_USEFUL:
        if pattern.search(body):
            useful_hits.append(label)
    for label, pattern in _COMPILED_NOISE:
        if pattern.search(body):
            noise_hits.append(label)

    lowered = body.lower()
    if any(word.lower() in lowered for word in extra_useful if word):
        useful_hits.append("自定义")
    if any(word.lower() in lowered for word in extra_noise if word):
        noise_hits.append("自定义")

    # 强噪音直接否掉（骂人、找对象、打探钱、广告）
    hard_noise = [label for label in noise_hits if label in HARD_NOISE_LABELS]
    if hard_noise:
        return Verdict(
            useful=False,
            score=-5,
            useful_hits=useful_hits,
            noise_hits=noise_hits,
            note=f"强噪音：{'、'.join(hard_noise)}",
        )

    score = 2 * len(useful_hits) - 2 * len(noise_hits)
    # 弱信号（提问/打听）最多加 1 分，避免「有没有人聊天」这种也算有用
    if _COMPILED_WEAK.search(body):
        score += 1
    # 用户自己在 config 里加的词，权重更高（就是「我关心的东西」）
    if "自定义" in useful_hits:
        score += 2
    if len(body) < MIN_MEANINGFUL_LEN:
        score -= 1
    if comment_count >= 5 and useful_hits:
        score += 1  # 有人在讨论，信息价值更高

    useful = score >= min_score
    note = "" if useful else ("内容过短" if len(body) < MIN_MEANINGFUL_LEN else "没有命中实用主题")
    return Verdict(
        useful=useful,
        score=score,
        useful_hits=useful_hits,
        noise_hits=noise_hits,
        note=note,
    )
