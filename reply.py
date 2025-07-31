import sys
import time
import random
import pickle
import os
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QPushButton, QTextEdit, QProgressBar, QLabel, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QColor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class ReplyThread(QThread):
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    summary_signal = pyqtSignal(int, int, int)
    notification_signal = pyqtSignal(str, str)

    def __init__(self, username, password, messages, cookie_file, dm_limit):
        super().__init__()
        self.username = username
        self.password = password
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

            self.status_signal.emit("Opening DM section...")
            self.log_signal.emit("Opening DM section...", "info")
            try:
                direct_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "svg[aria-label='Direct']"))
                )
                direct_button.click()
                time.sleep(random.uniform(2, 4))
                self.log_signal.emit("Clicked Direct button", "success")
            except Exception as e:
                self.log_signal.emit(f"Could not find Direct button: {str(e)}", "error")
                self.notification_signal.emit("Failed to open DM section", "error")
                return

            self.status_signal.emit("Collecting DM list...")
            self.log_signal.emit("Collecting DM list...", "info")
            user_elements = driver.find_elements(By.CSS_SELECTOR, "div.x1i10hfl.x1qjc9v5.xjqpnuy.xc5r6h4")
            if not user_elements:
                self.log_signal.emit("No DMs found in inbox.", "error")
                self.notification_signal.emit("No DMs found", "error")
                return

            self.log_signal.emit(f"Found {len(user_elements)} users in DM inbox", "success")
            self.progress_signal.emit(0)
            successful_replies = []
            failed_replies = []
            max_replies = min(len(user_elements), self.dm_limit)

            for i, user_element in enumerate(user_elements[:max_replies], 1):
                if not self.running:
                    return
                try:
                    # Attempt to extract username (optional, replace with correct selector if available)
                    try:
                        username = user_element.find_element(By.CSS_SELECTOR, "span[class*='username']").text
                    except:
                        username = f"User {i}"  # Fallback to User number if username not found
                    self.status_signal.emit(f"Replying to {username} ({i}/{max_replies})...")
                    self.log_signal.emit(f"Replying to {username} ({i}/{max_replies})...", "info")
                    # Click the entire user element instead of specific link
                    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.x1i10hfl.x1qjc9v5.xjqpnuy.xc5r6h4")))
                    user_element.click()
                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    self.log_signal.emit(f"Could not click on {username}: {str(e)}", "error")
                    self.notification_signal.emit(f"Failed to open chat for {username}", "error")
                    failed_replies.append(username)
                    self.summary_signal.emit(len(successful_replies), len(failed_replies), max_replies)
                    continue

                try:
                    textarea = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='Message'][contenteditable='true']"))
                    )
                    textarea.click()
                    message = random.choice(self.messages)
                    if not self.type_like_human(textarea, message):
                        return
                    self.log_signal.emit(f"Typed message for {username}", "success")
                except Exception as e:
                    self.log_signal.emit(f"Could not find or type in Message box for {username}: {str(e)}", "error")
                    self.notification_signal.emit(f"Failed to reply to {username}", "error")
                    failed_replies.append(username)
                    self.summary_signal.emit(len(successful_replies), len(failed_replies), max_replies)
                    continue

                try:
                    send_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//div[text()='Send']"))
                    )
                    send_button.click()
                    self.log_signal.emit(f"Replied to {username}", "success")
                    self.notification_signal.emit(f"Replied to {username}", "success")
                    successful_replies.append(username)
                except Exception as e:
                    self.log_signal.emit(f"Could not find Send button for {username}: {str(e)}", "error")
                    self.notification_signal.emit(f"Failed to reply to {username}", "error")
                    failed_replies.append(username)
                    self.summary_signal.emit(len(successful_replies), len(failed_replies), max_replies)
                    continue

                self.progress_signal.emit(i)
                self.summary_signal.emit(len(successful_replies), len(failed_replies), max_replies)
                time.sleep(random.uniform(10, 20))

                if i % 5 == 0:
                    pause_time = random.uniform(120, 300)
                    self.log_signal.emit(f"Pausing for {pause_time/60:.1f} minutes after {i} replies...", "info")
                    for _ in range(int(pause_time)):
                        if not self.running:
                            return
                        time.sleep(1)

            self.log_signal.emit(f"Bot finished! Summary: {len(successful_replies)} replies sent successfully, {len(failed_replies)} failed.", "success")
            self.notification_signal.emit(f"Bot finished! {len(successful_replies)} replies sent", "success")
            if successful_replies:
                self.log_signal.emit(f"Successful replies: {', '.join(successful_replies)}", "success")
            if failed_replies:
                self.log_signal.emit(f"Failed replies: {', '.join(failed_replies)}", "error")
            self.status_signal.emit("Bot finished")
            self.summary_signal.emit(len(successful_replies), len(failed_replies), max_replies)
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
        if not self.username or not self.password:
            self.log_signal.emit("No username or password provided. Please enter in Main window.", "error")
            self.notification_signal.emit("No username or password provided", "error")
            raise ValueError("No username or password")
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
            self.notification_signal.emit(f"Manual login failed: {str(e)}", "error")
            raise

class ReplyDMWindow(QMainWindow):
    def __init__(self, is_dark_mode, cookie_file, username, password):
        super().__init__()
        self.setWindowTitle("Reply to DMs")
        self.setGeometry(200, 200, 600, 400)
        self.is_dark_mode = is_dark_mode
        self.cookie_file = cookie_file
        self.username = username
        self.password = password
        self.reply_thread = None
        self.settings_file = "E:/DOWNLOADS/InstagramBotPython/reply_settings.pkl"

        # UI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout()

        # Header
        self.header_layout = QHBoxLayout()
        self.logo_label = QLabel("Reply Messages")
        self.logo_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.header_layout.addWidget(self.logo_label)
        self.header_layout.addStretch()
        self.main_layout.addLayout(self.header_layout)

        # Input Card
        self.input_card = QWidget()
        self.input_card.setStyleSheet(self.get_card_style())
        self.input_layout = QGridLayout()
        self.input_layout.setSpacing(8)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Reply Messages (one per line)")
        self.message_input.setFixedHeight(80)
        self.message_input.setStyleSheet(self.get_input_style())
        self.input_layout.addWidget(QLabel("Messages:"), 0, 0)
        self.input_layout.addWidget(self.message_input, 0, 1)

        self.dm_limit_input = QLineEdit()
        self.dm_limit_input.setPlaceholderText("Enter DM Limit (10-100)")
        self.dm_limit_input.setStyleSheet(self.get_input_style())
        self.input_layout.addWidget(QLabel("Daily DM Limit:"), 1, 0)
        self.input_layout.addWidget(self.dm_limit_input, 1, 1)

        self.input_card.setLayout(self.input_layout)
        self.main_layout.addWidget(self.input_card)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/play_icon.png"))
        self.start_button.setFixedSize(100, 35)
        self.start_button.setStyleSheet(self.get_button_style())
        self.start_button.clicked.connect(self.start_reply)
        self.button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/stop_icon.png"))
        self.stop_button.setFixedSize(100, 35)
        self.stop_button.setStyleSheet(self.get_button_style())
        self.stop_button.clicked.connect(self.stop_reply)
        self.stop_button.setEnabled(False)
        self.button_layout.addWidget(self.stop_button)

        self.clear_logs_button = QPushButton("Clear")
        self.clear_logs_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/clear_icon.png"))
        self.clear_logs_button.setFixedSize(100, 35)
        self.clear_logs_button.setStyleSheet(self.get_button_style())
        self.clear_logs_button.clicked.connect(self.clear_logs)
        self.button_layout.addWidget(self.clear_logs_button)

        self.save_settings_button = QPushButton("Save")
        self.save_settings_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/save_icon.png"))
        self.save_settings_button.setFixedSize(100, 35)
        self.save_settings_button.setStyleSheet(self.get_button_style())
        self.save_settings_button.clicked.connect(self.save_settings)
        self.button_layout.addWidget(self.save_settings_button)
        self.main_layout.addLayout(self.button_layout)

        # Summary Label
        self.summary_label = QLabel("Replies Sent: 0 | Failed: 0 | Remaining: 0")
        self.summary_label.setStyleSheet(self.get_label_style())
        self.main_layout.addWidget(self.summary_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(self.get_progress_style())
        self.progress_bar.setValue(0)
        self.main_layout.addWidget(self.progress_bar)

        # Log Box
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setStyleSheet(self.get_input_style())
        self.logs.setFixedHeight(150)  # Limiting height to balance UI
        self.main_layout.addWidget(self.logs)

        # User Guide Box
        self.user_guide = QTextEdit()
        self.user_guide.setReadOnly(True)
        self.user_guide.setStyleSheet(self.get_input_style())
        self.user_guide.setFixedHeight(150)  # Adjust height for content
        self.user_guide.setHtml("""
            <h2 style='color: #2196F3;'>User Guide</h2>
            <p><b>Follow these steps to use the Reply DM Bot effectively:</b></p>
            <ul>
                <li><span style='color: #4CAF50;'>✅</span> <b>Messages</b>: Enter one or more reply messages, each on a new line (e.g., <i>Thanks for your message!</i>). The bot will randomly select one to send.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>DM Limit</b>: Set a daily reply limit between 10 and 100 to avoid Instagram restrictions.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Start Button</b>: Click to begin replying to users in your Instagram DM inbox.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Stop Button</b>: Click to stop the bot if needed.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Clear Button</b>: Click to clear the activity log.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Save Button</b>: Click to save your messages and DM limit for future use.</li>
            </ul>
            <p><b>Note:</b> Ensure a stable internet connection and valid Instagram credentials (provided in the main window) to avoid errors.</p>
        """)
        self.main_layout.addWidget(self.user_guide)

        self.central_widget.setLayout(self.main_layout)

        # Apply initial theme
        self.apply_theme()

        self.load_settings()

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
                QLabel {
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
                QLabel {
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
        self.input_card.setStyleSheet(self.get_card_style())
        self.message_input.setStyleSheet(self.get_input_style())
        self.dm_limit_input.setStyleSheet(self.get_input_style())
        self.start_button.setStyleSheet(self.get_button_style())
        self.stop_button.setStyleSheet(self.get_button_style())
        self.clear_logs_button.setStyleSheet(self.get_button_style())
        self.save_settings_button.setStyleSheet(self.get_button_style())
        self.logs.setStyleSheet(self.get_input_style())
        self.user_guide.setStyleSheet(self.get_input_style())  # Apply style to user guide
        self.summary_label.setStyleSheet(self.get_label_style())
        self.progress_bar.setStyleSheet(self.get_progress_style())
        self.logo_label.setStyleSheet(self.get_label_style())

    def log(self, message, message_type="info"):
        color = {"info": "#000000" if not self.is_dark_mode else "#FFFFFF",
                 "success": "#4CAF50",
                 "error": "#F44336"}.get(message_type, "#000000" if not self.is_dark_mode else "#FFFFFF")
        self.logs.append(f'<span style="color: {color}; font-family: Arial;">[{time.strftime("%H:%M:%S")}] {message}</span>')
        self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())

    def update_summary(self, successful, failed, total):
        self.summary_label.setText(f"Replies Sent: {successful} | Failed: {failed} | Remaining: {total - successful - failed}")

    def show_notification(self, message, message_type):
        msg = QMessageBox()
        msg.setWindowTitle("Notification")
        msg.setText(message)
        msg.setStyleSheet(self.get_notification_style())
        msg.exec_()

    def start_reply(self):
        if self.reply_thread and self.reply_thread.isRunning():
            self.log("Reply bot is already running!", "error")
            self.show_notification("Reply bot is already running!", "error")
            return

        messages = self.message_input.toPlainText().strip().split("\n")
        messages = [msg.strip() for msg in messages if msg.strip()]
        try:
            dm_limit = int(self.dm_limit_input.text())
            if dm_limit < 10 or dm_limit > 100:
                raise ValueError
        except ValueError:
            self.log("Please enter a valid DM limit (10-100)!", "error")
            self.show_notification("Invalid DM limit!", "error")
            return

        if not messages:
            self.log("Please enter at least one reply message!", "error")
            self.show_notification("Please enter at least one reply message!", "error")
            return

        self.reply_thread = ReplyThread(self.username, self.password, messages, self.cookie_file, dm_limit)
        self.reply_thread.log_signal.connect(self.log)
        self.reply_thread.progress_signal.connect(self.progress_bar.setValue)
        self.reply_thread.status_signal.connect(self.statusBar().showMessage)
        self.reply_thread.summary_signal.connect(self.update_summary)
        self.reply_thread.notification_signal.connect(self.show_notification)
        self.reply_thread.finished_signal.connect(self.reply_finished)
        self.reply_thread.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.statusBar().showMessage("Starting reply bot...")
        self.log("Starting reply bot...", "info")
        self.summary_label.setText("Replies Sent: 0 | Failed: 0 | Remaining: 0")

    def stop_reply(self):
        if self.reply_thread:
            self.reply_thread.running = False
            self.reply_thread.wait()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("Reply bot stopped")
        self.log("Reply bot stopped by user", "error")
        self.show_notification("Reply bot stopped by user", "error")

    def reply_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("Ready")
        self.reply_thread = None

    def clear_logs(self):
        self.logs.clear()
        self.log("Logs cleared", "success")
        self.show_notification("Logs cleared", "success")

    def save_settings(self):
        settings = {
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
                self.message_input.setText(settings.get("messages", ""))
                self.dm_limit_input.setText(str(settings.get("dm_limit", 50)))
                self.log("Settings loaded successfully", "success")
            except Exception as e:
                self.log(f"Error loading settings: {str(e)}", "error")