"""狐友 Web 端接口常量。

来源：https://hy.sns.sohu.com 前端产物（Nuxt 3，CDN: hy.cdn.sohucs.com/hy-web/prod/_nuxt/）
反查方法见 README「接口来源」一节。这些值属于前端硬编码，服务端升级后可能变化，
变化时同步修改本文件即可，其余代码不需要动。
"""

# ---- 前端硬编码的 App 凭证（公开在 JS bundle 里，不属于任何用户的私密信息）----
APP_ID: int = 330012
APP_KEY: str = "1U32034rUs20A064"
APP_KEY_VS: str = "6.24.0"  # 前端版本号，参与签名
P_APPID: str = "110503"  # P-APPID 头

# ---- 三个业务网关 ----
BASE_CS = "https://cs-ol.sns.sohu.com"  # 内容服务：圈子、动态、评论（主要用这个）
BASE_OP = "https://op-ol.sns.sohu.com"  # 运营服务
BASE_DM = "https://dm-ol.sns.sohu.com"  # 数据/推荐服务

# ---- 通行证（登录相关，不参与签名）----
PASSPORT_HOME = "https://passport.sohu.com"  # 首次访问会下发 gidinf（设备号）
PASSPORT_QR_POLL = "https://pol.passport.sohu.com/passportapi/polling/apptkbyhy"

# ---- 响应状态 ----
STATUS_OK = 100000
STATUS_LOGIN_REQUIRED = {304023, 40110, 200004, 200003}
STATUS_ACCOUNT_BLOCKED = {320002, 320003}

# ---- 前端在请求里固定带的模板过滤参数（决定返回哪些类型的动态）----
TPL_WITH_HOT_RCMD = "1,2,3,4,26,29"
TPL_DEFAULT = "1,2,3,4,26"
STPL_DEFAULT = "1,2,3,4,7,9,11,12,13,16"

# ---- 排序方式 ----
SORT_NEW = 2  # 新发
SORT_REPLY = 4  # 新回（有新评论的）
SORT_HOT = 1  # 热门
SORT_ELITE = 3  # 精华
SORT_LABELS = {
    "new": SORT_NEW,
    "reply": SORT_REPLY,
    "hot": SORT_HOT,
    "elite": SORT_ELITE,
}

# ---- 圈子分类 category_type（来自 /v9/circle/category/list）----
# 注意语义：category_type=1 是「兴趣分类」，要再带 category_id 才能取到该分类下的圈子；
# category_type=2 是「热门圈子」聚合，category_type=3 是「新圈速报」，都不带 category_id。
CATEGORY_TYPE_TOPIC = 1
CATEGORY_TYPE_HOT_AGG = 2
CATEGORY_TYPE_NEW_AGG = 3
CAMPUS_CATEGORY_ID = "4"  # 兴趣分类里的「校园」

# ---- 可点击的网页链接模板（前端路由：/ 与 /circle/:circleId，帖子详情是 ?feedDetail=）----
FEED_URL = "https://hy.sns.sohu.com/?feedDetail={feed_id}"
CIRCLE_URL = "https://hy.sns.sohu.com/circle/{circle_id}"

# ---- Cookie 名（与前端一致的登录态）----
COOKIE_TOKEN = "pchytk"  # 登录 token
COOKIE_UID = "hyuid"  # 用户 id
COOKIE_UID_ALT = "pchypp"  # S-PPID 用的用户 id
COOKIE_GID = "gidinf"  # 设备号

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
