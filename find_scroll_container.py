#!/usr/bin/env python3
"""스크롤 컨테이너 찾기"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    url = "https://map.naver.com/p/search/청주 한의원"
    driver.get(url)
    time.sleep(10)

    # iframe으로 전환
    iframe = driver.find_element(By.ID, "searchIframe")
    driver.switch_to.frame(iframe)
    print("✅ iframe 전환 완료\n")

    # 스크롤 가능한 요소 찾기
    script = """
    function findScrollableElements() {
        const all = document.querySelectorAll('*');
        const scrollable = [];

        for (let el of all) {
            const style = window.getComputedStyle(el);
            const overflow = style.overflow + style.overflowY;

            if (overflow.includes('scroll') || overflow.includes('auto')) {
                if (el.scrollHeight > el.clientHeight) {
                    scrollable.push({
                        tag: el.tagName,
                        id: el.id,
                        class: el.className,
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight
                    });
                }
            }
        }
        return scrollable;
    }
    return findScrollableElements();
    """

    scrollable = driver.execute_script(script)

    print("=== 스크롤 가능한 요소들 ===")
    for i, el in enumerate(scrollable, 1):
        print(f"{i}. <{el['tag'].lower()}> id='{el['id']}' class='{el['class']}'")
        print(f"   scrollHeight: {el['scrollHeight']}, clientHeight: {el['clientHeight']}")
        print()

finally:
    driver.quit()
