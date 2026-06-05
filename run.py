#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
四川大学URP课程容量查询工具 (独立版)
SCU URP Course Capacity Query Tool (Standalone)

功能：查询四川大学各课程的信息
作者：@Elessar2077 with Codex
版本：1.1.0
"""

import requests
import json
import os
import sys
import hashlib
import argparse
import re
from datetime import datetime

# ============ 配置常量 ============

# URP系统URL
LOGIN_URL = "http://zhjw.scu.edu.cn/login"
SECURITY_CHECK_URL = "http://zhjw.scu.edu.cn/j_spring_security_check"
CAPTCHA_URL = "http://zhjw.scu.edu.cn/img/captcha.jpg"

# 选课页面（仅开放期间可用）
COURSE_SELECT_URL = "http://zhjw.scu.edu.cn/student/courseSelect/courseSelect/index"
FREE_COURSE_SELECT_URL = "http://zhjw.scu.edu.cn/student/courseSelect/freeCourse/courseList"

# 课程课表查询页面（常年可用）
COURSE_SCHEDULE_URL = "http://zhjw.scu.edu.cn/student/integratedQuery/course/courseSchdule/index"
COURSE_SCHEDULE_QUERY_URL = "http://zhjw.scu.edu.cn/student/integratedQuery/course/courseSchdule/courseInfo"

#使用"教学资源"接口，不能返回课容量等信息
#COURSE_SCHEDULE_URL = "http://zhjw.scu.edu.cn/student/teachingResources/courseCurriculum/index"
#OURSE_SCHEDULE_QUERY_URL = "http://zhjw.scu.edu.cn/student/teachingResources/courseCurriculum/search"

# HTTP请求头
# HTTP请求头
HTTP_HEAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 "
                  "Safari/537.36 Edg/105.0.1343.33"
}

# 查询课程数据的模板（选课页面）
QUERY_CLASS_DATA = {
    "kkxsh": "",
    "kch": "",
    "kcm": "",
    "skjs": "",
    "kclbdm": "",
    "xq": "0",
    "jc": "0"
}

# 课程课表查询数据模板（课表查询页面）
COURSE_SCHEDULE_DATA = {
    "zxjxjhh": "2025-2026-2-1",  # 执行教学计划号，默认当前学期
    "kch": "",      # 课程号
    "kcm": "",      # 课程名
    "skjs": "",     # 上课教师
    "kkxsh": "",    # 开课学院号
    "xq": "0",      # 校区
    "jc": "0",      # 节次
    "pageNum": "1",
    "pageSize": "100"
}


# ============ 日志工具 ============

def print_log(message: str, level: str = "INFO") -> None:
    """
    打印格式化日志，带时间戳和级别标记
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lvl = (level or "INFO").upper()
    if lvl not in {"SUCCESS", "INFO", "DEBUG", "ERROR"}:
        lvl = "INFO"
    prefix = {
        "SUCCESS": "[+]",
        "INFO": "[*]",
        "ERROR": "[!]",
        "DEBUG": "[DEBUG]"
    }.get(lvl, "[*]")
    print(f"[{ts}]{prefix} {message}")


# ============ 配置管理 ============

def get_config_path() -> str:
    """
    获取配置文件路径
    """
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, "config.json")


def load_config(path: str) -> dict:
    """
    从指定路径加载JSON配置
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"配置文件不存在: {path}\n"
            "请复制 config.json.example 为 config.json 并填写相关信息。"
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: str, config: dict) -> None:
    """
    保存JSON配置
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def is_valid_term(term: str) -> bool:
    """
    校验执行教学计划号格式: 2025-2026-2-1
    """
    if not isinstance(term, str):
        return False

    match = re.fullmatch(r"(\d{4})-(\d{4})-([12])-1", term.strip())
    if not match:
        return False

    start_year = int(match.group(1))
    end_year = int(match.group(2))
    return end_year == start_year + 1


def current_term_from_date(now=None) -> str:
    """
    根据当前日期推断学期号。
    9-12月为当学年第1学期，2-8月为上一学年第2学期，1月仍按上一学年第1学期处理。
    """
    now = now or datetime.now()
    year = now.year
    month = now.month

    if month >= 9:
        start_year = year
        term = 1
    elif month == 1:
        start_year = year - 1
        term = 1
    else:
        start_year = year - 1
        term = 2

    return f"{start_year}-{start_year + 1}-{term}-1"


def expand_term_shortcut(value: str):
    """
    将 25-2 或 2025-2 这样的短码展开为 2025-2026-2-1。
    """
    value = value.strip()
    match = re.fullmatch(r"(\d{2}|\d{4})-([12])", value)
    if not match:
        return None

    year_text = match.group(1)
    start_year = int(year_text)
    if len(year_text) == 2:
        start_year += 2000

    term = int(match.group(2))
    return f"{start_year}-{start_year + 1}-{term}-1"


def shift_term(term: str, step: int) -> str:
    """
    在当前学期号基础上前后切换一个学期。
    """
    if not is_valid_term(term):
        term = current_term_from_date()

    start_year_text, _, term_text, _ = term.split("-")
    start_year = int(start_year_text)
    term_no = int(term_text)

    if step > 0:
        if term_no == 1:
            term_no = 2
        else:
            start_year += 1
            term_no = 1
    else:
        if term_no == 2:
            term_no = 1
        else:
            start_year -= 1
            term_no = 2

    return f"{start_year}-{start_year + 1}-{term_no}-1"


def parse_term_input(value: str, current_term: str) -> tuple:
    """
    解析 /term 命令参数，返回 (term, error)。
    """
    value = value.strip().lower()

    if value == "now":
        return current_term_from_date(), None
    if value == "next":
        return shift_term(current_term, 1), None
    if value in {"prev", "previous"}:
        return shift_term(current_term, -1), None

    expanded = expand_term_shortcut(value)
    if expanded:
        return expanded, None

    if is_valid_term(value):
        return value, None

    return None, "学期格式无效。可用 /term 25-2、/term now、/term next、/term prev。"


def apply_configured_term(config: dict) -> None:
    """
    从配置中应用已保存的学期偏好。
    """
    term = str(config.get("zxjxjhh", "")).strip()
    if not term:
        return

    if is_valid_term(term):
        COURSE_SCHEDULE_DATA["zxjxjhh"] = term
    else:
        print_log(f"config.json 中的 zxjxjhh 无效，继续使用默认学期: {COURSE_SCHEDULE_DATA['zxjxjhh']}", "ERROR")


def print_term_help() -> None:
    """
    显示 /term 命令说明。
    """
    print_log(f"当前查询学期: {COURSE_SCHEDULE_DATA['zxjxjhh']}", "INFO")
    print_log("/term 用法:", "INFO")
    print("  /term                 显示当前学期和帮助")
    print("  /term now             自动切到当前日期对应学期")
    print("  /term 25-2            切到 2025-2026 学年第 2 学期")
    print("  /term 2025-2          切到 2025-2026 学年第 2 学期")
    print("  /term next            切到下一学期")
    print("  /term prev            切到上一学期")
    print("  /term 2025-2026-2-1   使用完整教学计划号")
    print("切换成功后会写入 config.json，下次启动继续使用。")


def handle_term_command(command: str, config_path: str, config: dict) -> None:
    """
    处理交互模式中的 /term 命令。
    """
    parts = command.split(maxsplit=1)
    if len(parts) == 1 or parts[1].strip().lower() in {"help", "-h", "--help", "?"}:
        print_term_help()
        return

    term, error = parse_term_input(parts[1], COURSE_SCHEDULE_DATA["zxjxjhh"])
    if error:
        print_log(error, "ERROR")
        print_term_help()
        return

    COURSE_SCHEDULE_DATA["zxjxjhh"] = term
    config["zxjxjhh"] = term
    try:
        save_config(config_path, config)
    except OSError as exc:
        print_log(f"保存学期偏好失败: {exc}", "ERROR")
        return

    print_log(f"已切换查询学期: {term}（已保存，下次启动继续使用）", "SUCCESS")


# ============ 加密工具 ============

def encrypt_password(content: str) -> str:
    """
    使用URP系统的双重MD5加密密码
    """
    magic_str = "{Urp602019}"
    res1 = hashlib.md5((content + magic_str).encode()).hexdigest()
    res1 = hashlib.md5(res1.encode()).hexdigest()
    res2 = hashlib.md5(content.encode()).hexdigest()
    res2 = hashlib.md5(res2.encode()).hexdigest()
    return res1 + "*" + res2


# ============ 登录模块 ============

def user_login(session: requests.Session, username: str, password: str) -> requests.Session:
    """
    使用配置的凭据登录URP系统
    """
    try:
        import ddddocr
    except ImportError:
        print_log("错误：缺少 ddddocr 模块，请运行: pip install ddddocr", "ERROR")
        sys.exit(1)
    
    ocr = ddddocr.DdddOcr(show_ad=False)
    login_attempts = 0
    max_attempts = 100
    
    while login_attempts < max_attempts:
        # 获取登录页面
        res = session.get(LOGIN_URL, headers=HTTP_HEAD)
        if res.status_code != 200:
            print_log("获取登录页面失败", "ERROR")
            login_attempts += 1
            continue
        
        # 提取token
        token_pos = res.text.find("tokenValue")
        if token_pos == -1:
            print_log("无法找到token，页面可能已更改", "ERROR")
            sys.exit(1)
        token = res.text[token_pos + 37: token_pos + 69]
        
        # 加密密码
        encrypted_pw = encrypt_password(password)
        
        # 获取验证码
        captcha_resp = session.get(CAPTCHA_URL, headers=HTTP_HEAD)
        captcha_code = ocr.classification(captcha_resp.content)
        
        # 准备登录数据
        login_data = {
            "lang": "zh",
            "tokenValue": token,
            "j_username": username,
            "j_password": encrypted_pw,
            "j_captcha": captcha_code
        }
        
        # 提交登录
        res = session.post(SECURITY_CHECK_URL, data=login_data, headers=HTTP_HEAD)
        
        if res.text.find('验证码错误') != -1:
            print_log("验证码不正确，正在重试...", "INFO")
            login_attempts += 1
            continue
        elif res.text.find('token校验失败') != -1:
            print_log("token校验失败", "ERROR")
            sys.exit(1)
        elif res.text.find('用户名或密码错误!') == -1:
            print_log("登录成功！", "SUCCESS")
            return session
        else:
            print_log("账号或密码错误", "ERROR")
            sys.exit(1)
    
    print_log("登录尝试次数过多", "ERROR")
    sys.exit(1)


# ============ 课程查询模块 ============

def sanitize_text(value: str) -> str:
    """
    标准化文本输入，去除无法编码为UTF-8的字符
    """
    if not isinstance(value, str):
        return str(value) if value else ""
    cleaned = value.encode("utf-8", "ignore").decode("utf-8", "ignore")
    return cleaned


def query_course_capacity_select(session: requests.Session, keyword: str, search_field: str = "kcm") -> list:
    """
    通过选课页面查询课程容量（仅选课开放期间可用）
    """
    class_list = []
    clean_keyword = sanitize_text(keyword)

    if not clean_keyword.strip():
        print_log("课程关键词为空，跳过查询。", "ERROR")
        return []

    # 复制查询模板并设置查询字段
    local_query = QUERY_CLASS_DATA.copy()
    local_query[search_field] = clean_keyword

    # 首先访问选课页面获取会话
    res = session.get(COURSE_SELECT_URL, headers=HTTP_HEAD)
    if res.status_code != 200 or res.text.find("自由选课") == -1:
        print_log("选课页面未开放或无法访问", "INFO")
        return None  # 返回None表示选课页面不可用

    print_log("成功进入选课页面，正在查询课程列表...", "SUCCESS")

    # 发送课程查询请求
    res_post = session.post(
        FREE_COURSE_SELECT_URL,
        data=local_query,
        headers=HTTP_HEAD
    )

    if res_post.status_code != 200:
        print_log(f"获取课程列表失败，状态码: {res_post.status_code}", "ERROR")
        return []

    raw_text = res_post.text or ""
    if not raw_text.strip():
        print_log("课程列表响应为空，可能网络异常或登录过期。", "ERROR")
        return []

    # 解析JSON响应
    try:
        res_json = json.loads(raw_text)
    except json.JSONDecodeError:
        snippet = raw_text.strip()[:200]
        print_log("课程列表响应不是有效的JSON格式。", "ERROR")
        print_log(f"响应片段: {snippet}", "DEBUG")
        return []

    if not isinstance(res_json, dict):
        print_log("课程列表响应格式异常，无法解析。", "ERROR")
        return []

    if "rwRxkZlList" not in res_json:
        print_log("课程列表响应缺少 rwRxkZlList 字段。", "ERROR")
        return []

    # 解析课程列表
    rw_rxk_zl_list = res_json['rwRxkZlList']
    if isinstance(rw_rxk_zl_list, str):
        try:
            class_list = json.loads(rw_rxk_zl_list)
        except json.JSONDecodeError:
            print_log("课程列表字段解析失败。", "ERROR")
            return []
    elif isinstance(rw_rxk_zl_list, list):
        class_list = rw_rxk_zl_list
    else:
        print_log("课程列表数据类型错误。", "ERROR")
        return []

    return class_list


def normalize_course_records(courses: list) -> list:
    """
    Add lowercase aliases for the newer courseCurriculum API fields.
    """
    aliases = {
        "KCH": "kch",
        "KXH": "kxh",
        "KCM": "kcm",
        "JSM": "skjs",
        "SKJS": "skjs",
        "XF": "xf",
        "XS": "xs",
        "KCLBMC": "kclbmc",
        "KCLBDM": "kclbdm",
        "KKXSH": "kkxsh",
        "KKXSM": "kkxsm",
        "ZXJXJHH": "zxjxjhh",
        "ZXJXJHM": "zxjxjhm",
        "KSLXMC": "kslxmc",
        "KSLXDM": "kslxdm",
        "RN": "rn",
    }

    normalized = []
    for course in courses:
        if not isinstance(course, dict):
            continue

        item = course.copy()
        for source_field, target_field in aliases.items():
            if target_field not in item and source_field in item:
                item[target_field] = item[source_field]
        normalized.append(item)

    return normalized


def query_course_capacity_schedule(session: requests.Session, keyword: str, search_field: str = "kcm") -> list:
    """
    通过课程课表查询页面查询课程信息（常年可用，但可能没有实时容量数据）
    """
    class_list = []
    clean_keyword = sanitize_text(keyword)

    if not clean_keyword.strip():
        print_log("课程关键词为空，跳过查询。", "ERROR")
        return []

    # 复制查询模板并设置查询字段
    local_query = COURSE_SCHEDULE_DATA.copy()
    local_query[search_field] = clean_keyword

    # 访问课程课表查询页面
    res = session.get(COURSE_SCHEDULE_URL, headers=HTTP_HEAD)
    if res.status_code != 200:
        print_log("进入课程课表查询页面失败！", "ERROR")
        return []

    print_log("使用课程课表查询页面（选课页面未开放）...", "INFO")

    # 课表查询需要特定的请求头
    schedule_headers = HTTP_HEAD.copy()
    schedule_headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "http://zhjw.scu.edu.cn",
        #"Referer": "http://zhjw.scu.edu.cn/student/integratedQuery/course/courseSchdule/index"
        "Referer": "http://zhjw.scu.edu.cn/student/teachingResources/courseCurriculum/index"
    })

    # 发送课程查询请求
    res_post = session.post(
        COURSE_SCHEDULE_QUERY_URL,
        data=local_query,
        headers=schedule_headers
    )

    if res_post.status_code != 200:
        print_log(f"获取课程列表失败，状态码: {res_post.status_code}", "ERROR")
        return []

    raw_text = res_post.text or ""
    if not raw_text.strip():
        print_log("课程列表响应为空。", "ERROR")
        return []

    # 调试输出（仅在DEBUG模式显示）
    #print_log(f"响应状态码: {res_post.status_code}", "DEBUG")
    #print_log(f"响应内容前200字符: {raw_text[:200]}", "DEBUG")

    # 解析JSON响应
    try:
        res_json = json.loads(raw_text)
    except json.JSONDecodeError:
        snippet = raw_text.strip()[:200]
        print_log("课程列表响应不是有效的JSON格式。", "ERROR")
        print_log(f"响应片段: {snippet}", "DEBUG")
        return []

    # 课表查询页面的返回格式: {"list": {"records": [...]}}
    if isinstance(res_json, dict):
        if isinstance(res_json.get("records"), list):
            class_list = res_json["records"]
        elif isinstance(res_json.get("pageContext"), dict):
            page_context = res_json["pageContext"]
            if isinstance(page_context.get("records"), list):
                class_list = page_context["records"]
            else:
                print_log(f"pageContext 字段不是课程列表，字段: {list(page_context.keys())}", "ERROR")
                return []
        elif "list" in res_json and isinstance(res_json["list"], dict):
            list_data = res_json["list"]
            if isinstance(list_data.get("records"), list):
                class_list = list_data["records"]
            elif isinstance(list_data.get("rows"), list):
                class_list = list_data["rows"]
            else:
                print_log(f"list 字段不是课程列表，字段: {list(list_data.keys())}", "ERROR")
                return []
        elif isinstance(res_json.get("list"), list):
            class_list = res_json["list"]
        elif isinstance(res_json.get("data"), list):
            class_list = res_json["data"]
        elif isinstance(res_json.get("data"), dict):
            data = res_json["data"]
            if isinstance(data.get("records"), list):
                class_list = data["records"]
            elif isinstance(data.get("rows"), list):
                class_list = data["rows"]
            elif isinstance(data.get("list"), list):
                class_list = data["list"]
            else:
                print_log(f"data 字段不是课程列表，字段: {list(data.keys())}", "ERROR")
                return []
        elif isinstance(res_json.get("rows"), list):
            class_list = res_json["rows"]
        else:
            print_log(f"无法识别课程列表字段，响应字段: {list(res_json.keys())}", "ERROR")
            return []
    elif isinstance(res_json, list):
        class_list = res_json
    else:
        print_log("课程列表数据类型错误。", "ERROR")
        return []

    class_list = normalize_course_records(class_list)

    # 课表查询页面的字段名与选课页面一致，直接使用
    # 字段包括: kch, kxh, kcm, skjs, xf, xs, bkskrl, bkskyl 等
    return class_list


def query_course_capacity(session: requests.Session, keyword: str, search_field: str = "kcm") -> tuple:
    """
    根据课程名称关键词查询课程列表及其容量信息
    优先使用选课页面（有实时容量），如未开放则使用课表查询页面

    返回:
        (课程列表, 查询来源) - 查询来源: "select" 或 "schedule"
    """
    # 首先尝试选课页面（有实时容量数据）
    result = query_course_capacity_select(session, keyword, search_field)

    if result is not None:
        return result, "select"

    # 如果选课页面返回None（未开放），则使用课表查询页面
    print_log("选课页面未开放，切换到课程课表查询页面...", "INFO")
    result = query_course_capacity_schedule(session, keyword, search_field)

    return (result, "schedule") if result is not None else ([], "none")


def display_course_capacity(courses: list) -> None:
    """
    格式化显示课程容量信息，包括课容量和课余量
    注意：课表查询页面可能没有实时容量数据
    """
    if not courses:
        print_log("未找到相关课程。", "INFO")
        return

    # 检查是否有容量数据
    has_capacity_data = any(
        course.get('bkskrl') is not None or course.get('bkskyl') is not None
        for course in courses
    )

    if has_capacity_data:
        # 有容量数据的显示格式
        print("\n" + "=" * 110)
        print(f"{'序号':<6}{'课程号':<12}{'课序号':<8}{'课程名称':<26}{'教师':<10}{'课容量':<8}{'课余量':<8}{'已选':<6}")
        print("-" * 110)
    else:
        # 无容量数据的显示格式（课表查询页面）
        print("\n" + "=" * 90)
        print(f"{'序号':<6}{'课程号':<12}{'课序号':<8}{'课程名称':<30}{'教师':<12}{'学分':<6}{'学时':<6}")
        print("-" * 90)
        print_log("提示：当前使用课表查询页面，不显示实时容量数据", "INFO")

    for idx, course in enumerate(courses, 1):
        # 获取课程基本信息
        course_id = course.get('kch') or ''
        seq_num = course.get('kxh') or ''
        name = course.get('kcm') or ''
        teacher = course.get('skjs') or ''

        if has_capacity_data:
            # 获取容量信息
            total_capacity = course.get('bkskrl')
            remaining = course.get('bkskyl')

            # 处理容量数据
            if total_capacity is None:
                total_capacity_str = "-"
            else:
                try:
                    total_capacity = int(total_capacity)
                    total_capacity_str = str(total_capacity)
                except (ValueError, TypeError):
                    total_capacity_str = "-"

            if remaining is None:
                remaining_str = "-"
                selected_str = "-"
            else:
                try:
                    remaining = int(remaining)
                    remaining_str = str(remaining)
                    if total_capacity_str != "-":
                        selected_str = str(int(total_capacity_str) - remaining)
                    else:
                        selected_str = "-"
                except (ValueError, TypeError):
                    remaining_str = "-"
                    selected_str = "-"

            # 截断过长的文本
            name = name[:24] if len(name) > 24 else name
            teacher = teacher[:8] if len(teacher) > 8 else teacher

            # 格式化输出
            print(f"{idx:<6}{course_id:<12}{seq_num:<8}{name:<26}{teacher:<10}"
                  f"{total_capacity_str:<8}{remaining_str:<8}{selected_str:<6}")
        else:
            # 无容量数据的显示
            xf = course.get('xf', '-')
            xs = course.get('xs', '-')

            # 截断过长的文本
            name = name[:28] if len(name) > 28 else name
            teacher = teacher[:10] if len(teacher) > 10 else teacher

            print(f"{idx:<6}{course_id:<12}{seq_num:<8}{name:<30}{teacher:<12}{str(xf):<6}{str(xs):<6}")

    if has_capacity_data:
        print("=" * 110)
    else:
        print("=" * 90)
    print_log(f"共找到 {len(courses)} 门课程", "SUCCESS")


def display_course_detail(course: dict) -> None:
    """
    显示单门课程的详细信息
    """
    print("\n" + "-" * 60)
    print(f"课程名称: {course.get('kcm', 'N/A')}")
    print(f"课程号: {course.get('kch', 'N/A')}")
    print(f"课序号: {course.get('kxh', 'N/A')}")
    print(f"教师: {course.get('skjs', 'N/A')}")
    print(f"学分: {course.get('xf', 'N/A')}")
    print(f"学时: {course.get('xs', 'N/A')}")
    print(f"课容量: {course.get('bkskrl', 'N/A')}")
    print(f"课余量: {course.get('bkskyl', 'N/A')}")
    print(f"校区: {course.get('kkxqm', 'N/A')}")
    print(f"教学楼: {course.get('jxlm', 'N/A')}")
    print(f"教室: {course.get('jasm', 'N/A')}")
    print(f"上课周次: {course.get('zcsm', 'N/A')}")
    print(f"课程类别: {course.get('kclbmc', 'N/A')}")
    print("-" * 60)


# ============ 主程序 ============

def interactive_mode(session: requests.Session, config_path: str, config: dict):
    """
    交互式查询模式
    """
    print()
    print_log("=" * 50, "INFO")
    print_log("进入交互式查询模式", "INFO")
    print_log("命令: [关键词] 按课程名称查询 | [-t 教师名] 按授课教师查询 | [d+序号] 查看详情 | [q] 退出", "INFO")
    print_log(f"当前查询学期: {COURSE_SCHEDULE_DATA['zxjxjhh']}；输入 /term 查看或切换学期", "INFO")
    print_log("/term 示例: /term now 当前学期 | /term 25-2 指定学年学期 | /term next/prev 前后切换", "INFO")
    print_log("=" * 50, "INFO")
    
    last_courses = []
    
    while True:
        print()
        user_input = input("请输入命令: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() == 'q':
            print_log("感谢使用，再见！", "INFO")
            break

        if user_input.lower() == "/term" or user_input.lower().startswith("/term "):
            handle_term_command(user_input, config_path, config)
            continue
        
        # 查看详情命令
        if user_input.lower().startswith('d') and len(user_input) > 1:
            try:
                idx = int(user_input[1:]) - 1
                if 0 <= idx < len(last_courses):
                    display_course_detail(last_courses[idx])
                else:
                    print_log("无效的序号", "ERROR")
            except ValueError:
                print_log("无效的命令格式", "ERROR")
            continue
        
        # 查询课程；输入 "-t 教师名" 时按授课教师查询
        search_field = "kcm"
        query_text = user_input
        if user_input.startswith("-t "):
            search_field = "skjs"
            query_text = user_input[3:].strip()
            if not query_text:
                print_log("请输入教师姓名，例如: -t 张三", "ERROR")
                continue

        search_label = "授课教师" if search_field == "skjs" else "课程名称"
        print_log(f"正在按{search_label}查询: '{query_text}' ...", "INFO")
        courses, source = query_course_capacity(session, query_text, search_field)
        last_courses = courses
        if source == "schedule":
            print_log("提示：当前使用课表查询页面，容量数据可能不是实时的", "INFO")
        display_course_capacity(courses)
        
        if courses:
            print_log("提示: 输入 d+序号 (如 d1) 查看课程详情", "INFO")


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(
        description='四川大学URP课程容量查询工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  uv run query              # 交互式模式
  uv run query -k "高等数学" # 直接查询指定关键词
  uv run query --keyword "英语"

交互模式命令:
  [关键词]    按课程名称查询
  -t 教师名   按授课教师查询
  d+序号      查看课程详情 (如 d1)
  /term       查看学期切换帮助
  /term now   自动切到当前日期对应学期
  /term 25-2  切到 2025-2026 学年第 2 学期
  /term next  切到下一学期
  /term prev  切到上一学期
  q           退出程序
        '''
    )
    
    parser.add_argument(
        '-k', '--keyword',
        type=str,
        help='课程名称关键词（不指定则进入交互式模式）'
    )
    
    args = parser.parse_args()
    
    # 显示欢迎信息
    print_log("=" * 60, "INFO")
    print_log("四川大学URP课程容量查询工具", "INFO")
    print_log("=" * 60, "INFO")
    
    # 加载配置
    config_path = get_config_path()
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        print_log(str(e), "ERROR")
        sys.exit(1)
    apply_configured_term(config)
    
    username = config.get("username", "").strip()
    password = config.get("password", "").strip()
    
    if not username or not password:
        print_log("错误：请在 config.json 中配置用户名和密码。", "ERROR")
        sys.exit(1)
    
    print_log(f"使用账号: {username}", "INFO")
    print_log(f"当前查询学期: {COURSE_SCHEDULE_DATA['zxjxjhh']}", "INFO")
    print_log("正在登录URP系统...", "INFO")
    
    # 创建会话并登录
    session = requests.Session()
    session = user_login(session, username, password)
    
    if args.keyword:
        # 直接查询模式
        print_log(f"正在查询关键词: '{args.keyword}' ...", "INFO")
        courses, source = query_course_capacity(session, args.keyword)
        if source == "schedule":
            print_log("提示：当前使用课表查询页面，容量数据可能不是实时的", "INFO")
        display_course_capacity(courses)
    else:
        # 交互式模式
        interactive_mode(session, config_path, config)


if __name__ == "__main__":
    main()
