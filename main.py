import sys
import time
import random
import pickle
import os
import csv
import requests  # Added for control.txt fetching
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLineEdit, QPushButton, QTextEdit, QProgressBar, QStatusBar, QLabel, 
                             QDockWidget, QListWidget, QListWidgetItem, QMessageBox, QStyledItemDelegate)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from reply import ReplyDMWindow
from follow_unfollow import FollowUnfollowWindow
from analytics import AnalyticsWindow

os.environ["QT_LOGGING_RULES"] = "qt5.warning=false"

def check_control_file():
    try:
        print("Attempting to fetch control.txt...")
        response = requests.get('https://raw.githubusercontent.com/rudi2005/InstagramDMBot-New/main/control.txt', timeout=5)
        print(f"Response status code: {response.status_code}")
        if response.status_code == 200:
            status = response.text.strip().lower()
            print(f"Control.txt content: {status}")
            if status == 'inactive':
                print("Bot is disabled (control.txt is set to 'inactive'). Exiting...")
                sys.exit(0)
            elif status == 'active':
                print("Bot is enabled (control.txt is set to 'active'). Starting...")
            else:
                print("Invalid control.txt content. Expected 'active' or 'inactive'. Exiting...")
                sys.exit(1)
        else:
            print(f"Failed to fetch control.txt. Status code: {response.status_code}. Exiting...")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking control.txt: {str(e)}. Exiting...")
        sys.exit(1)

class SidebarDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(Qt.UserRole) == "coming_soon":
            font = option.font
            font.setWeight(QFont.Normal)
            option.font = font

class BotThread(QThread):
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    summary_signal = pyqtSignal(int, int, int)
    notification_signal = pyqtSignal(str, str)
    stats_signal = pyqtSignal(list, list)

    def __init__(self, username, password, reel_url, messages, cookie_file, dm_limit):
        super().__init__()
        self.username = username
        self.password = password
        self.reel_url = reel_url
        self.messages = messages
        self.cookie_file = cookie_file
        self.dm_limit = dm_limit
        self.running = True

    def run(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-notifications")
        options.add_argument("--start-maximized")
        options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.158 Safari/537.36")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

        try:
            self.status_signal.emit("Navigating to Instagram...")
            self.log_signal.emit("Navigating to Instagram...", "info")
            driver.get("https://www.instagram.com")
            WebDriverWait(driver, 45).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(random.uniform(2, 4))

            if self.load_cookies(driver):
                self.log_signal.emit("Attempting to login with cookies...", "info")
                driver.refresh()
                time.sleep(random.uniform(2, 4))
                if "instagram.com/accounts/login" not in driver.current_url:
                    self.log_signal.emit("Logged in using cookies!", "success")
                else:
                    self.log_signal.emit("Cookies invalid, performing manual login...", "info")
                    self.perform_manual_login(driver)
            else:
                self.log_signal.emit("No cookies found, performing manual login...", "info")
                self.perform_manual_login(driver)

            try:
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[text()='Not Now']"))
                ).click()
                self.log_signal.emit("Clicked 'Not Now' on Save Info or Notifications popup", "success")
            except:
                self.log_signal.emit("No popups found", "info")

            self.status_signal.emit("Navigating to reel...")
            self.log_signal.emit(f"Navigating to reel: {self.reel_url}", "info")
            driver.get(self.reel_url)
            WebDriverWait(driver, 45).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(random.uniform(3, 6))

            self.status_signal.emit("Checking for comment section...")
            self.log_signal.emit("Checking for comment section...", "info")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.xdj266r.x14z9mp.xat24cr.x1lziwak"))
                )
                self.log_signal.emit("Scrolling comments...", "info")
                for _ in range(10):
                    if not self.running:
                        return
                    driver.execute_script("document.querySelector('div.xdj266r.x14z9mp.xat24cr.x1lziwak')?.scrollBy(0, 1000);")
                    time.sleep(random.uniform(1, 2))
            except:
                self.log_signal.emit("Comment section not found. Trying alternative method...", "error")
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(random.uniform(2, 4))
                except:
                    self.log_signal.emit("Alternative scrolling failed. No comments available.", "error")

            self.status_signal.emit("Extracting commenters...")
            self.log_signal.emit("Extracting commenters...", "info")
            commenters = driver.execute_script("""
                let comments = document.querySelectorAll('a._a6hd[href*="/"]');
                if (comments.length === 0) {
                    return [];
                }
                return Array.from(comments)
                    .filter(c => {
                        const username = c.getAttribute('href').split('/')[1];
                        return username && /^[a-zA-Z0-9._]{3,}$/.test(username) && !['reels', 'explore', 'p'].includes(username);
                    })
                    .map(c => c.getAttribute('href').split('/')[1])
                    .filter((value, index, self) => self.indexOf(value) === index);
            """)

            if not commenters:
                self.log_signal.emit("No valid commenters found. Check if the reel URL is correct or has valid usernames.", "error")
                return

            self.log_signal.emit(f"Found {len(commenters)} valid commenters. Starting DM process...", "success")
            self.progress_signal.emit(0)
            successful_dms = []
            failed_dms = []
            max_dms = min(len(commenters), self.dm_limit)

            csv_file = "E:/DOWNLOADS/InstagramBotPython/dm_log.csv"
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if os.stat(csv_file).st_size == 0:
                    writer.writerow(["Timestamp", "Username", "Action", "Status"])

            for i, commenter in enumerate(commenters[:max_dms], 1):
                if not self.running:
                    return
                self.status_signal.emit(f"Sending DM to {commenter} ({i}/{max_dms})...")
                self.log_signal.emit(f"Sending DM to {commenter} ({i}/{max_dms})...", "info")
                driver.get(f"https://www.instagram.com/{commenter}")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(random.uniform(2, 4))

                try:
                    message_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//div[text()='Message']"))
                    )
                    message_button.click()
                except:
                    try:
                        driver.find_element(By.XPATH, "//svg[@aria-label='Options']").click()
                        WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[text()='Send message']"))
                        ).click()
                    except:
                        self.log_signal.emit(f"Could not find Message button for {commenter}. It might be a private account. Skipping...", "error")
                        self.notification_signal.emit(f"Failed to DM {commenter}", "error")
                        failed_dms.append(commenter)
                        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Failed"])
                        self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
                        self.stats_signal.emit(successful_dms, failed_dms)
                        continue

                try:
                    textarea = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='Message']"))
                    )
                    textarea.click()
                    message = random.choice(self.messages)
                    if not self.type_like_human(textarea, message):
                        return
                    self.log_signal.emit(f"Typed message for {commenter}", "success")
                except:
                    self.log_signal.emit(f"Could not find or type in Message box for {commenter}. Skipping...", "error")
                    self.notification_signal.emit(f"Failed to DM {commenter}", "error")
                    failed_dms.append(commenter)
                    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Failed"])
                    self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
                    self.stats_signal.emit(successful_dms, failed_dms)
                    continue

                try:
                    send_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='Send']"))
                    )
                    send_button.click()
                    self.log_signal.emit(f"DM sent to {commenter}", "success")
                    self.notification_signal.emit(f"DM sent to {commenter}", "success")
                    successful_dms.append(commenter)
                    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Success"])
                except:
                    self.log_signal.emit(f"Could not find Send button for {commenter}. Skipping...", "error")
                    self.notification_signal.emit(f"Failed to DM {commenter}", "error")
                    failed_dms.append(commenter)
                    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Failed"])
                    self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
                    self.stats_signal.emit(successful_dms, failed_dms)
                    continue

                self.progress_signal.emit(i)
                self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
                self.stats_signal.emit(successful_dms, failed_dms)
                time.sleep(random.uniform(10, 20))

                if i % 5 == 0:
                    pause_time = random.uniform(120, 300)
                    self.log_signal.emit(f"Pausing for {pause_time/60:.1f} minutes after {i} DMs...", "info")
                    for _ in range(int(pause_time)):
                        if not self.running:
                            return
                        time.sleep(1)

            self.log_signal.emit(f"Bot finished! Summary: {len(successful_dms)} DMs sent successfully, {len(failed_dms)} failed.", "success")
            self.notification_signal.emit(f"Bot finished! {len(successful_dms)} DMs sent", "success")
            if successful_dms:
                self.log_signal.emit(f"Successful DMs: {', '.join(successful_dms)}", "success")
            if failed_dms:
                self.log_signal.emit(f"Failed DMs: {', '.join(failed_dms)}", "error")
            self.status_signal.emit("Bot finished")
            self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
            self.stats_signal.emit(successful_dms, failed_dms)
            self.finished_signal.emit()

        finally:
            self.save_cookies(driver)
            self.log_signal.emit("Closing browser...", "info")
            self.status_signal.emit("Closing browser...")
            time.sleep(2)
            driver.quit()

    def type_like_human(self, element, text):
        for char in text:
            if not self.running:
                return False
            element.send_keys(char)
            time.sleep(random.uniform(0.4, 0.6))
        return True

    def save_cookies(self, driver):
        try:
            with open(self.cookie_file, 'wb') as file:
                pickle.dump(driver.get_cookies(), file)
            self.log_signal.emit("Cookies saved for future logins", "success")
        except Exception as e:
            self.log_signal.emit(f"Error saving cookies: {str(e)}", "error")

    def load_cookies(self, driver):
        if os.path.exists(self.cookie_file) and os.path.getsize(self.cookie_file) > 0:
            try:
                with open(self.cookie_file, 'rb') as file:
                    cookies = pickle.load(file)
                    for cookie in cookies:
                        driver.add_cookie(cookie)
                self.log_signal.emit("Cookies loaded successfully", "success")
                return True
            except Exception as e:
                self.log_signal.emit(f"Error loading cookies: {str(e)}. Falling back to manual login.", "error")
                return False
        else:
            self.log_signal.emit("No valid cookie file found. Performing manual login...", "info")
            return False

    def perform_manual_login(self, driver):
        try:
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            self.type_like_human(username_field, self.username)
            self.type_like_human(password_field, self.password)
            driver.find_element(By.XPATH, "//button[@type='submit']").click()
            WebDriverWait(driver, 45).until(EC.url_contains("instagram.com"))
            time.sleep(random.uniform(2, 4))
            self.log_signal.emit("Manual login successful", "success")
        except Exception as e:
            self.log_signal.emit(f"Manual login failed: {str(e)}", "error")
            raise

class InstagramBotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Instagram DM Bot")
        self.setGeometry(100, 100, 800, 600)
        self.cookie_file = "E:/DOWNLOADS/InstagramBotPython/instagram_cookies.pkl"
        self.settings_file = "E:/DOWNLOADS/InstagramBotPython/settings.pkl"
        self.bot_thread = None
        self.successful_dms = []
        self.failed_dms = []
        self.is_dark_mode = False
        self.reply_window = None
        self.follow_unfollow_window = None
        self.analytics_window = None

        # UI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout()

        # Sidebar
        self.sidebar = QDockWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setFixedHeight(1000)
        self.sidebar.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.sidebar_content = QListWidget()
        self.sidebar_content.setItemDelegate(SidebarDelegate(self.sidebar_content))
        self.sidebar_content.setStyleSheet(self.get_sidebar_style())
        self.add_sidebar_items()
        self.sidebar_content.currentRowChanged.connect(self.switch_page)
        self.sidebar.setWidget(self.sidebar_content)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar)

        # Pages
        self.main_page = QWidget()
        self.settings_page = QWidget()
        self.pages = [self.main_page, self.settings_page]
        self.current_page = 0

        # Main Page
        self.main_layout_inner = QVBoxLayout()
        self.header_layout = QHBoxLayout()
        self.logo_label = QLabel()
        logo_path = "E:/DOWNLOADS/InstagramBotPython/logo.png"
        if os.path.exists(logo_path):
            self.logo_label.setPixmap(QPixmap(logo_path))
            self.logo_label.setScaledContents(True)
            self.logo_label.setFixedSize(150, 50)
        else:
            self.logo_label.setText("DM Bot")
            self.logo_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.logo_label.setStyleSheet(self.get_logo_style())
        self.header_layout.addWidget(self.logo_label)

        # Mode Switch Button
        self.mode_button = QPushButton()
        self.mode_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/mode_icon.png"))
        self.mode_button.setFixedSize(35, 35)
        self.mode_button.setStyleSheet(self.get_button_style())
        self.mode_button.clicked.connect(self.toggle_mode)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.mode_button)
        self.main_layout_inner.addLayout(self.header_layout)

        # Input Fields
        self.input_card = QWidget()
        self.input_card.setStyleSheet(self.get_card_style())
        self.input_layout = QGridLayout()
        self.input_layout.setSpacing(8)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setStyleSheet(self.get_input_style())
        self.input_layout.addWidget(QLabel("Username:"), 0, 0)
        self.input_layout.addWidget(self.username_input, 0, 1)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet(self.get_input_style())
        self.input_layout.addWidget(QLabel("Password:"), 1, 0)
        self.input_layout.addWidget(self.password_input, 1, 1)

        self.reel_url_input = QLineEdit()
        self.reel_url_input.setPlaceholderText("Reel URL")
        self.reel_url_input.setStyleSheet(self.get_input_style())
        self.input_layout.addWidget(QLabel("Reel URL:"), 2, 0)
        self.input_layout.addWidget(self.reel_url_input, 2, 1)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Messages (one per line)")
        self.message_input.setFixedHeight(80)
        self.message_input.setStyleSheet(self.get_input_style())
        self.input_layout.addWidget(QLabel("Messages:"), 3, 0)
        self.input_layout.addWidget(self.message_input, 3, 1)
        self.input_card.setLayout(self.input_layout)
        self.main_layout_inner.addWidget(self.input_card)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/save_icon.png"))
        self.save_button.setFixedSize(100, 35)
        self.save_button.setStyleSheet(self.get_button_style())
        self.save_button.clicked.connect(self.save_settings)
        self.button_layout.addWidget(self.save_button)

        self.start_button = QPushButton("Start")
        self.start_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/play_icon.png"))
        self.start_button.setFixedSize(100, 35)
        self.start_button.setStyleSheet(self.get_button_style())
        self.start_button.clicked.connect(self.start_bot)
        self.button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/stop_icon.png"))
        self.stop_button.setFixedSize(100, 35)
        self.stop_button.setStyleSheet(self.get_button_style())
        self.stop_button.clicked.connect(self.stop_bot)
        self.stop_button.setEnabled(False)
        self.button_layout.addWidget(self.stop_button)

        self.clear_logs_button = QPushButton("Clear")
        self.clear_logs_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/clear_icon.png"))
        self.clear_logs_button.setFixedSize(100, 35)
        self.clear_logs_button.setStyleSheet(self.get_button_style())
        self.clear_logs_button.clicked.connect(self.clear_logs)
        self.button_layout.addWidget(self.clear_logs_button)
        self.main_layout_inner.addLayout(self.button_layout)

        # DM Summary Label
        self.summary_label = QLabel("DMs Sent: 0 | Failed: 0 | Remaining: 0")
        self.summary_label.setStyleSheet(self.get_label_style())
        self.main_layout_inner.addWidget(self.summary_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(self.get_progress_style())
        self.progress_bar.setValue(0)
        self.main_layout_inner.addWidget(self.progress_bar)

        # Activity Log Box
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setStyleSheet(self.get_input_style())
        self.logs.setFixedHeight(150)
        self.main_layout_inner.addWidget(self.logs)

        # User Guide Box
        self.user_guide = QTextEdit()
        self.user_guide.setReadOnly(True)
        self.user_guide.setStyleSheet(self.get_input_style())
        self.user_guide.setFixedHeight(200)
        self.user_guide.setHtml("""
            <h2 style='color: #2196F3;'>User Guide</h2>
            <p><b>Follow these steps to use the Instagram DM Bot effectively:</b></p>
            <ul>
                <li><span style='color: #4CAF50;'>✅</span> <b>Username</b>: Enter your Instagram username (e.g., <i>your_username</i>) without the '@' symbol.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Password</b>: Enter your Instagram account password. Ensure it is correct and keep it secure.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Reel URL</b>: Copy the full URL of an Instagram reel (e.g., <i>https://www.instagram.com/reel/ABC123/</i>) from the browser or app. The bot will extract commenters from this reel.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Messages</b>: Write one or more messages, each on a new line. The bot will randomly select one message to send to each commenter (e.g., <i>Hello! Thanks for your comment!</i>).</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>DM Limit</b>: Set a daily DM limit between 10 and 200 in the Settings page to avoid Instagram restrictions.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Save Button</b>: Click to save your inputs for future use.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Start Button</b>: Click to begin sending DMs to reel commenters.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Scrolling Manually</b>: Ensure Scroll Manually Use (Mouse & Trackpad) Loading All Comments.</li>                
                <li><span style='color: #4CAF50;'>✅</span> <b>Stop Button</b>: Click to stop the bot if needed.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Clear Button</b>: Click to clear the activity log.</li>
            </ul>
            <p><b>Note:</b> Ensure a stable internet connection and valid Instagram credentials to avoid errors.</p>
        """)
        self.main_layout_inner.addWidget(self.user_guide)

        self.main_page.setLayout(self.main_layout_inner)

        # Settings Page
        self.settings_layout = QVBoxLayout()
        self.dm_limit_label = QLabel("Daily DM Limit:")
        self.dm_limit_label.setStyleSheet(self.get_label_style())
        self.settings_layout.addWidget(self.dm_limit_label)

        self.dm_limit_input = QLineEdit()
        self.dm_limit_input.setPlaceholderText("Enter DM Limit (10-200)")
        self.dm_limit_input.setStyleSheet(self.get_input_style())
        self.settings_layout.addWidget(self.dm_limit_input)

        self.password_settings_input = QLineEdit()
        self.password_settings_input.setPlaceholderText("Password")
        self.password_settings_input.setEchoMode(QLineEdit.Password)
        self.password_settings_input.setStyleSheet(self.get_input_style())
        self.settings_layout.addWidget(QLabel("Password:"))
        self.settings_layout.addWidget(self.password_settings_input)

        self.save_settings_button = QPushButton("Save")
        self.save_settings_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/save_icon.png"))
        self.save_settings_button.setFixedSize(100, 35)
        self.save_settings_button.setStyleSheet(self.get_button_style())
        self.save_settings_button.clicked.connect(self.save_settings)
        self.settings_layout.addWidget(self.save_settings_button)
        self.settings_layout.addStretch()
        self.settings_page.setLayout(self.settings_layout)

        # Add main page to layout
        self.main_layout.addWidget(self.main_page)
        self.central_widget.setLayout(self.main_layout)

        # Status Bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        self.statusBar.setStyleSheet(self.get_label_style())

        # Apply initial theme
        self.apply_theme()

        # Load settings
        self.load_settings()

    def add_sidebar_items(self):
        items = [
            ("Main", "main_icon.png"),
            ("Settings", "settings_icon.png"),
            ("Analytics", "analytics_icon.png"),
            ("Reply DMs", "reply_icon.png"),
            ("Follow/Unfollow", "follow_icon.png"),
            ("COMING SOON", "coming_soon.png"),
            ("Schedule Posts", "schedule_icon.png"),
            ("Auto Like", "like_icon.png"),
            ("Comment Bot", "comment_icon.png"),
            ("Profile Analytics", "profile_icon.png"),
            ("Hashtag Generator", "hashtag_icon.png"),
            ("Loginsta™ © 2025.", "powered_by_icon.png")
        ]
        for text, icon in items:
            item = QListWidgetItem()
            item.setText(text)
            if icon:
                item.setIcon(QIcon(f"E:/DOWNLOADS/InstagramBotPython/icons/{icon}"))
            if text == "COMING SOON":
                item.setData(Qt.UserRole, "coming_soon")
            self.sidebar_content.addItem(item)

    def get_sidebar_style(self):
        if self.is_dark_mode:
            return """
                QListWidget {
                    background: #263238;
                    border: 1px solid #B0BEC5;
                    font-family: Arial;
                    font-size: 16px;
                    font-weight: bold;
                    color: #FFFFFF;
                    border-radius: 5px;
                }
                QListWidget::item {
                    padding: 8px;
                    border: none;
                    font-weight: bold;
                }
                QListWidget::item:selected {
                    background: #37474F;
                    color: #FFFFFF;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QListWidget::item:hover {
                    background: #455A64;
                    font-weight: bold;
                    border-radius: 5px;
                }
            """
        else:
            return """
                QListWidget {
                    background: #FFFFFF;
                    border: 1px solid #B0BEC5;
                    font-family: Arial;
                    font-size: 16px;
                    font-weight: bold;
                    color: #000000;
                    border-radius: 5px;
                }
                QListWidget::item {
                    padding: 8px;
                    border: none;
                    font-weight: bold;
                }
                QListWidget::item:selected {
                    background: #E3F2FD;
                    color: #000000;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QListWidget::item:hover {
                    background: #F5F7FA;
                    font-weight: bold;
                    border-radius: 5px;
                }
            """

    def get_card_style(self):
        if self.is_dark_mode:
            return """
                QWidget {
                    background: #37474F;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    padding: 10px;
                }
            """
        else:
            return """
                QWidget {
                    background: #FFFFFF;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    padding: 10px;
                }
            """

    def get_input_style(self):
        if self.is_dark_mode:
            return """
                QLineEdit, QTextEdit {
                    padding: 8px;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    background: #455A64;
                    color: #FFFFFF;
                    font-family: Arial;
                    font-size: 16px;
                }
                QLineEdit:focus, QTextEdit:focus {
                    border: 1px solid #4FC3F7;
                    background: #546E7A;
                }
            """
        else:
            return """
                QLineEdit, QTextEdit {
                    padding: 8px;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    background: #FFFFFF;
                    color: #000000;
                    font-family: Arial;
                    font-size: 16px;
                }
                QLineEdit:focus, QTextEdit:focus {
                    border: 1px solid #2196F3;
                    background: #F5F7FA;
                }
            """

    def get_button_style(self):
        if self.is_dark_mode:
            return """
                QPushButton {
                    background: transparent;
                    color: #FFFFFF;
                    padding: 6px;
                    border-radius: 5px;
                    font-family: Arial;
                    font-size: 16px;
                    border: 1px solid #B0BEC5;
                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
                }
                QPushButton:hover {
                    background: #4FC3F7;
                    border: 1px solid #4FC3F7;
                    color: #000000;
                }
            """
        else:
            return """
                QPushButton {
                    background: transparent;
                    color: #000000;
                    padding: 6px;
                    border-radius: 5px;
                    font-family: Arial;
                    font-size: 16px;
                    border: 1px solid #B0BEC5;
                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
                }
                QPushButton:hover {
                    background: #2196F3;
                    border: 1px solid #2196F3;
                    color: #FFFFFF;
                }
            """

    def get_label_style(self):
        if self.is_dark_mode:
            return """
                QLabel, QStatusBar {
                    color: #FFFFFF;
                    font-family: Arial;
                    font-size: 16px;
                    background: #263238;
                    border-radius: 5px;
                    padding: 6px;
                }
            """
        else:
            return """
                QLabel, QStatusBar {
                    color: #000000;
                    font-family: Arial;
                    font-size: 16px;
                    background: #FFFFFF;
                    border-radius: 5px;
                    padding: 6px;
                }
            """

    def get_progress_style(self):
        if self.is_dark_mode:
            return """
                QProgressBar {
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    background: #455A64;
                    text-align: center;
                    color: #FFFFFF;
                    font-family: Arial;
                    font-size: 16px;
                }
                QProgressBar::chunk {
                    background: #4FC3F7;
                    border-radius: 5px;
                }
            """
        else:
            return """
                QProgressBar {
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    background: #FFFFFF;
                    text-align: center;
                    color: #000000;
                    font-family: Arial;
                    font-size: 16px;
                }
                QProgressBar::chunk {
                    background: #2196F3;
                    border-radius: 5px;
                }
            """

    def get_logo_style(self):
        if self.is_dark_mode:
            return """
                QLabel {
                    color: #FFFFFF;
                    font-family: Arial;
                    font-size: 24px;
                    background: #263238;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    padding: 8px;
                }
            """
        else:
            return """
                QLabel {
                    color: #000000;
                    font-family: Arial;
                    font-size: 24px;
                    background: #FFFFFF;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    padding: 8px;
                }
            """

    def get_notification_style(self):
        if self.is_dark_mode:
            return """
                QMessageBox {
                    background: #37474F;
                    color: #FFFFFF;
                    font-family: Arial;
                    font-size: 16px;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                }
                QMessageBox QPushButton {
                    background: transparent;
                    color: #FFFFFF;
                    padding: 6px;
                    border-radius: 5px;
                    font-family: Arial;
                    font-size: 16px;
                    border: 1px solid #B0BEC5;
                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
                }
                QMessageBox QPushButton:hover {
                    background: #4FC3F7;
                    border: 1px solid #4FC3F7;
                    color: #000000;
                }
            """
        else:
            return """
                QMessageBox {
                    background: #FFFFFF;
                    color: #000000;
                    font-family: Arial;
                    font-size: 16px;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                }
                QMessageBox QPushButton {
                    background: transparent;
                    color: #000000;
                    padding: 6px;
                    border-radius: 5px;
                    font-family: Arial;
                    font-size: 16px;
                    border: 1px solid #B0BEC5;
                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
                }
                QMessageBox QPushButton:hover {
                    background: #2196F3;
                    border: 1px solid #2196F3;
                    color: #FFFFFF;
                }
            """

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background: %s;
            }
        """ % ("#263238" if self.is_dark_mode else "#F5F7FA"))
        self.sidebar_content.setStyleSheet(self.get_sidebar_style())
        self.input_card.setStyleSheet(self.get_card_style())
        self.username_input.setStyleSheet(self.get_input_style())
        self.password_input.setStyleSheet(self.get_input_style())
        self.reel_url_input.setStyleSheet(self.get_input_style())
        self.message_input.setStyleSheet(self.get_input_style())
        self.save_button.setStyleSheet(self.get_button_style())
        self.start_button.setStyleSheet(self.get_button_style())
        self.stop_button.setStyleSheet(self.get_button_style())
        self.clear_logs_button.setStyleSheet(self.get_button_style())
        self.logs.setStyleSheet(self.get_input_style())
        self.user_guide.setStyleSheet(self.get_input_style())
        self.summary_label.setStyleSheet(self.get_label_style())
        self.progress_bar.setStyleSheet(self.get_progress_style())
        self.dm_limit_label.setStyleSheet(self.get_label_style())
        self.dm_limit_input.setStyleSheet(self.get_input_style())
        self.password_settings_input.setStyleSheet(self.get_input_style())
        self.save_settings_button.setStyleSheet(self.get_button_style())
        self.statusBar.setStyleSheet(self.get_label_style())
        self.logo_label.setStyleSheet(self.get_logo_style())
        if self.reply_window:
            self.reply_window.is_dark_mode = self.is_dark_mode
            self.reply_window.apply_theme()
        if self.follow_unfollow_window:
            self.follow_unfollow_window.is_dark_mode = self.is_dark_mode
            self.follow_unfollow_window.apply_theme()
        if self.analytics_window:
            self.analytics_window.is_dark_mode = self.is_dark_mode
            self.analytics_window.apply_theme()

    def toggle_mode(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()
        self.log(f"Switched to {'Dark' if self.is_dark_mode else 'Normal'} mode", "success")
        self.show_notification(f"Switched to {'Dark' if self.is_dark_mode else 'Normal'} mode", "success")

    def switch_page(self, index):
        try:
            if index == 2:  # Analytics
                if not self.analytics_window:
                    self.analytics_window = AnalyticsWindow(self.is_dark_mode)
                self.analytics_window.show()
            elif index == 3:  # Reply DMs
                if not self.reply_window:
                    username = self.username_input.text().strip()
                    password = self.password_input.text().strip()
                    if not all([username, password]):
                        self.log("Please enter username and password in the main page or save in settings!", "error")
                        self.show_notification("Please enter username and password!", "error")
                        return
                    self.reply_window = ReplyDMWindow(self.is_dark_mode, self.cookie_file, username, password)
                self.reply_window.show()
            elif index == 4:  # Follow/Unfollow
                if not self.follow_unfollow_window:
                    username = self.username_input.text().strip()
                    password = self.password_input.text().strip()
                    if not all([username, password]):
                        self.log("Please enter username and password in the main page or save in settings!", "error")
                        self.show_notification("Please enter username and password!", "error")
                        return
                    self.follow_unfollow_window = FollowUnfollowWindow(self.is_dark_mode, self.cookie_file, username, password)
                self.follow_unfollow_window.show()
            elif index in [5, 6, 7, 8, 9]:  # New features
                self.log("Feature coming soon!", "info")
                self.show_notification("Feature coming soon!", "info")
            else:
                for i, page in enumerate(self.pages):
                    page.hide() if i != index else page.show()
                self.current_page = index
        except Exception as e:
            self.log(f"Error opening page: {str(e)}", "error")
            self.show_notification(f"Error opening page: {str(e)}", "error")

    def log(self, message, message_type="info"):
        color = {"info": "#000000" if not self.is_dark_mode else "#FFFFFF",
                 "success": "#4CAF50",
                 "error": "#F44336"}.get(message_type, "#000000" if not self.is_dark_mode else "#FFFFFF")
        self.logs.append(f'<span style="color: {color}; font-family: Arial;">[{time.strftime("%H:%M:%S")}] {message}</span>')
        self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())

    def update_summary(self, successful, failed, total):
        self.summary_label.setText(f"DMs Sent: {successful} | Failed: {failed} | Remaining: {total - successful - failed}")

    def show_notification(self, message, message_type):
        msg = QMessageBox()
        msg.setWindowTitle("Notification")
        msg.setText(message)
        msg.setStyleSheet(self.get_notification_style())
        msg.exec_()

    def update_stats(self, successful_dms, failed_dms):
        self.successful_dms = successful_dms
        self.failed_dms = failed_dms

    def start_bot(self):
        if self.bot_thread and self.bot_thread.isRunning():
            self.log("Bot is already running!", "error")
            self.show_notification("Bot is already running!", "error")
            return

        username = self.username_input.text()
        password = self.password_input.text()
        reel_url = self.reel_url_input.text()
        messages = self.message_input.toPlainText().strip().split("\n")
        messages = [msg.strip() for msg in messages if msg.strip()]
        try:
            dm_limit = int(self.dm_limit_input.text())
            if dm_limit < 10 or dm_limit > 200:
                raise ValueError
        except ValueError:
            self.log("Please enter a valid DM limit (10-200)!", "error")
            self.show_notification("Invalid DM limit!", "error")
            return

        if not all([username, password, reel_url, messages]):
            self.log("Please fill all fields!", "error")
            self.show_notification("Please fill all fields!", "error")
            return

        self.bot_thread = BotThread(username, password, reel_url, messages, self.cookie_file, dm_limit)
        self.bot_thread.log_signal.connect(self.log)
        self.bot_thread.progress_signal.connect(self.progress_bar.setValue)
        self.bot_thread.status_signal.connect(self.statusBar.showMessage)
        self.bot_thread.summary_signal.connect(self.update_summary)
        self.bot_thread.notification_signal.connect(self.show_notification)
        self.bot_thread.stats_signal.connect(self.update_stats)
        self.bot_thread.finished_signal.connect(self.bot_finished)
        self.bot_thread.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.statusBar.showMessage("Starting bot...")
        self.log("Starting bot...", "info")
        self.summary_label.setText("DMs Sent: 0 | Failed: 0 | Remaining: 0")

    def stop_bot(self):
        if self.bot_thread:
            self.bot_thread.running = False
            self.bot_thread.wait()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar.showMessage("Bot stopped")
        self.log("Bot stopped by user", "error")
        self.show_notification("Bot stopped by user", "error")

    def bot_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar.showMessage("Ready")
        self.bot_thread = None

    def clear_logs(self):
        self.logs.clear()
        self.log("Logs cleared", "success")
        self.show_notification("Logs cleared", "success")

    def save_settings(self):
        settings = {
            "username": self.username_input.text(),
            "password": self.password_input.text() or self.password_settings_input.text(),
            "reel_url": self.reel_url_input.text(),
            "messages": self.message_input.toPlainText(),
            "dm_limit": self.dm_limit_input.text()
        }
        try:
            with open(self.settings_file, 'wb') as file:
                pickle.dump(settings, file)
            self.log("Settings saved successfully", "success")
            self.show_notification("Settings saved successfully", "success")
        except Exception as e:
            self.log(f"Error saving settings: {str(e)}", "error")
            self.show_notification(f"Error saving settings: {str(e)}", "error")

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'rb') as file:
                    settings = pickle.load(file)
                self.username_input.setText(settings.get("username", ""))
                self.password_input.setText(settings.get("password", ""))
                self.reel_url_input.setText(settings.get("reel_url", ""))
                self.message_input.setText(settings.get("messages", ""))
                self.dm_limit_input.setText(str(settings.get("dm_limit", 50)))
                self.password_settings_input.setText(settings.get("password", ""))
                self.log("Settings loaded successfully", "success")
            except Exception as e:
                self.log(f"Error loading settings: {str(e)}", "error")

if __name__ == "__main__":
    check_control_file()  # Check control.txt before starting the app
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Arial", 16))
    window = InstagramBotApp()
    window.show()
    sys.exit(app.exec_())