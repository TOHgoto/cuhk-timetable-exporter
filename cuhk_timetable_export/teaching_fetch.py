"""
Fetch Teaching Timetable: open browser for user to enter captcha and search,
then read the result page and return its HTML for parsing/export.
"""
from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager

DEFAULT_TEACHING_URL = "https://rgsntl.rgs.cuhk.edu.hk/rws_prd_applx2/Public/tt_dsp_timetable.aspx"


import re

def _infer_subjects_from_courses(course_codes: list[str]) -> list[str]:
    """
    Infer unique Course Subject dropdown values from course list (e.g. ROSE5720 -> ROSE).
    """
    subs = []
    for code in course_codes:
        code = (code or "").strip()
        m = re.match(r"^([A-Z]{2,6})", code.upper())
        if m:
            s = m.group(1)
            if s not in subs:
                subs.append(s)
    return subs


def fetch_teaching_timetable_html(
    course_codes: list[str],
    url: str = DEFAULT_TEACHING_URL,
    captcha_callback: str | None = None,
) -> list[str]:
    """
    Open browser to Teaching Timetable; pre-fill subject from course_codes.
    User enters captcha and clicks Search. After they press Enter in terminal,
    read the result page and return its HTML. Loops for multiple subjects.
    """
    subjects = _infer_subjects_from_courses(course_codes)
    if not subjects:
        raise ValueError(
            "Could not infer subject code from course list (e.g. ROSE5720 -> ROSE). Check my_courses.txt."
        )

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(
            f"Could not start Chrome for Teaching Timetable. Install Chrome and run again. Error: {e}"
        ) from e

    try:
        htmls = []
        for i, subject in enumerate(subjects):
            if i > 0:
                print(f"\\n--- 准备获取下一个科目: {subject} ---")
            driver.get(url)
            driver.implicitly_wait(5)

            # Pre-fill Course Subject so user only needs to enter captcha and click Search
            try:
                sel = Select(driver.find_element(By.ID, "ddl_subject"))
                sel.select_by_value(subject)
            except Exception:
                pass  # page structure may vary; user can select manually

            print()
            print(f"请在浏览器中为科目 {subject}：")
            print("  1. 输入验证码（Verification Code）")
            print("  2. 点击 Search 按钮")
            print("  3. 等待课表结果加载完成")
            print("  4. 回到本终端，按回车键继续")
            print()
            input("完成上述步骤后按回车键 → ")

            html = driver.page_source
            if "gv_detail" not in html:
                raise ValueError(
                    f"当前页面不是科目 {subject} 的课表结果页（未检测到结果表格）。请先在浏览器中完成操作，再回到终端按回车。"
                )
            htmls.append(html)
        return htmls
    finally:
        driver.quit()


