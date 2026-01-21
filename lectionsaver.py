from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from pypdf import PdfMerger
import time
import os
import re

BASE_URL = "https://on.mmamos.ru"
LOGIN_URL = f"{BASE_URL}/login/index.php"
COURSES_URL = f"{BASE_URL}/my/courses.php"

EMAIL = "{ВАШ ЛОГИН}"
PASSWORD = "{ВАШ ПАРОЛЬ}"

OUTPUT_DIR = "pdf"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def login(page):
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.fill('input[name="username"]', EMAIL)
        page.fill('input[name="password"]', PASSWORD)
        page.click('input#loginbtn')
        page.wait_for_url("https://on.mmamos.ru/", timeout=60000)
        print(" Успешный вход")
    except PlaywrightTimeoutError:
        print(" Ошибка: таймаут при входе. Проверьте соединение и данные логина.")
        raise
    except Exception as e:
        print(f" Ошибка при входе: {e}")
        raise

def get_courses(page):
    try:
        page.goto(COURSES_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('a[href*="course/view.php?id="]', timeout=10000)
        links = page.eval_on_selector_all(
            'a[href*="course/view.php?id="]',
            'els => [...new Set(els.map(e => e.href))]'
        )
        return links
    except PlaywrightTimeoutError:
        print(" Ошибка: не удалось загрузить список курсов.")
        return []
    except Exception as e:
        print(f" Ошибка при получении курсов: {e}")
        return []

def get_lecture_links(page, course_url):
    try:
        page.goto(course_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('li.activity.modtype_page a.aalink', timeout=10000)
        links = page.eval_on_selector_all(
            'li.activity.modtype_page a.aalink',
            'els => els.map(e => e.href)'
        )
        return links
    except PlaywrightTimeoutError:
        print(f" Таймаут при загрузке курса {course_url}. Лекции будут пропущены.")
        return []
    except Exception as e:
        print(f" Ошибка при получении лекций {course_url}: {e}")
        return []

def get_course_title(page):
    try:
        page.wait_for_selector('h1.headermain', timeout=10000)
        title = page.eval_on_selector('h1.headermain', 'el => el.textContent.trim()')
        safe_title = re.sub(r'[^\w\d_-]', '_', title)
        return safe_title
    except PlaywrightTimeoutError:
        print(" Не удалось получить название курса, используем 'course_unknown'.")
        return "course_unknown"
    except Exception as e:
        print(f" Ошибка при получении названия курса: {e}")
        return "course_unknown"

def save_pdf(page, url, path, retries=3):
    if os.path.exists(path):
        print(f"     Уже скачано: {path}")
        return True
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            page.pdf(path=path, format="A4", print_background=True)
            print(f"     Сохранено: {path}")
            return True
        except PlaywrightTimeoutError:
            print(f"     Таймаут при загрузке лекции {url}, попытка {attempt}/{retries}")
        except Exception as e:
            print(f"     Ошибка при сохранении лекции {url}: {e}, попытка {attempt}/{retries}")
        time.sleep(2)
    print(f"     Не удалось сохранить лекцию {url} после {retries} попыток.")
    return False

def merge_pdfs(files, output):
    try:
        if not files:
            print(f" Нет файлов для объединения: {output}")
            return
        merger = PdfMerger()
        for f in files:
            merger.append(f)
        merger.write(output)
        merger.close()
        print(f"   Объединено: {output}")
    except Exception as e:
        print(f" Ошибка при объединении PDF {output}: {e}")


start_course_name = input("Введите название курса, с которого начать скачивание (например 'Информатика'): ").strip()
start_lecture_num = int(input("Введите номер лекции, с которой начать скачивание (например 6): ").strip())

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    try:
        login(page)
    except Exception:
        browser.close()
        exit(1)

    courses = get_courses(page)
    if not courses:
        print(" Нет доступных курсов.")
        browser.close()
        exit(1)

    start_course_found = False
    for idx, course_url in enumerate(courses, 1):
        try:
            page.goto(course_url, wait_until="domcontentloaded")
            course_name = get_course_title(page)
        except Exception:
            course_name = f"course_{idx}"
            print(f" Курс {idx}/{len(courses)}: {course_name} (название не удалось определить)")

        if not start_course_found:
            if start_course_name in course_name:
                start_course_found = True
            else:
                continue

        print(f" Курс {idx}/{len(courses)}: {course_name}")

        lecture_links = get_lecture_links(page, course_url)
        if not lecture_links:
            print(f"Нет лекций для курса {course_name}. Пропускаем.")
            continue

        pdfs = []
        for i, lecture_url in enumerate(lecture_links, 1):

            if course_name == start_course_name and i < start_lecture_num:
                continue
            pdf_path = f"{OUTPUT_DIR}/{course_name}_lecture{i}.pdf"
            success = save_pdf(page, lecture_url, pdf_path)
            if success:
                pdfs.append(pdf_path)

        output = f"{OUTPUT_DIR}/{course_name}_ALL.pdf"
        merge_pdfs(pdfs, output)

    browser.close()
    print("Конец работы. Выход...")
