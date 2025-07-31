import sys
import time
import random
import pickle
import os
import csv
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QPushButton, QProgressBar, QTextEdit, QLabel, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class FollowUnfollowThread(QThread):
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    summary_signal = pyqtSignal(int, int, int, str)
    notification_signal = pyqtSignal(str, str)

    def __init__(self, username, password, cookie_file, target_username, action, limit):
        super().__init__()
        self.username = username
        self.password = password
        self.cookie_file = cookie_file
        self.target_username = target_username
        self.action = action  # 'follow' or 'unfollow'
        self.limit = limit
        self.running = True

    def run(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-notifications")
        options.add_argument("--start-maximized")
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.158 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        ]
        options.add_argument(f"user-agent={random.choice(user_agents)}")
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

            target_username = self.target_username.lstrip('@')
            self.status_signal.emit(f"Navigating to {target_username}'s profile...")
            self.log_signal.emit(f"Navigating to {target_username}'s profile...", "info")
            driver.get(f"https://www.instagram.com/{target_username}/")
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(random.uniform(3, 5))

            # Check if profile is private
            try:
                private_message = driver.find_element(By.XPATH, "//h2[contains(text(), 'This Account is Private')]")
                self.log_signal.emit(f"Target profile {target_username} is private!", "error")
                self.notification_signal.emit(f"Cannot access {target_username}'s followers list: Account is private", "error")
                return
            except:
                self.log_signal.emit("Profile is public, proceeding...", "info")

            # Open followers or following list
            list_type = "followers" if self.action == "follow" else "following"
            self.status_signal.emit(f"Opening {list_type} list...")
            self.log_signal.emit(f"Opening {list_type} list...", "info")
            try:
                selectors = [
                    "//span[contains(text(), '{list_type}')]/ancestor::a",
                    "a[href*='/{list_type}/']",
                    "a.x1i10hfl",
                    "a._a6hd",
                    "li.x6s0dn4 a.x1i10hfl"
                ]
                list_button = None
                for selector in selectors:
                    try:
                        list_button = WebDriverWait(driver, 30).until(
                            EC.element_to_be_clickable((By.XPATH if selector.startswith("//") else By.CSS_SELECTOR, selector.format(list_type=list_type)))
                        )
                        break
                    except:
                        continue

                if not list_button:
                    raise Exception("No valid followers/following button found")

                list_button.click()
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog'].x1ja2u2z"))
                )
                self.log_signal.emit(f"Opened {list_type} dialog box", "success")
            except Exception as e:
                self.log_signal.emit(f"Failed to open {list_type} list: {str(e)}", "error")
                self.notification_signal.emit(f"Failed to open {list_type} list", "error")
                return

            # Check for private account followers message
            try:
                private_followers = driver.find_element(By.XPATH, "//span[contains(text(), 'Only') and contains(text(), 'can see all followers')]")
                self.log_signal.emit(f"Cannot access {target_username}'s followers list: Only {target_username} can see all followers", "error")
                self.notification_signal.emit(f"Cannot access {target_username}'s followers list: Only {target_username} can see all followers", "error")
                return
            except:
                self.log_signal.emit("Followers list accessible, proceeding...", "info")

            # Scroll and extract usernames
            self.status_signal.emit(f"Extracting {list_type}...")
            self.log_signal.emit(f"Extracting {list_type}...", "info")
            usernames = []
            last_height = driver.execute_script("return document.querySelector('div[role=\"dialog\"].x1ja2u2z').scrollHeight")
            max_scroll_attempts = 10
            attempt = 0
            while len(usernames) < self.limit and attempt < max_scroll_attempts:
                if not self.running:
                    return
                driver.execute_script("document.querySelector('div[role=\"dialog\"].x1ja2u2z').scrollBy(0, 1000);")
                time.sleep(random.uniform(2, 3))
                usernames = driver.execute_script("""
                    let users = document.querySelectorAll('span._ap3a, span.xnz67gz');
                    return Array.from(users)
                        .map(u => u.textContent)
                        .filter(u => u && /^[a-zA-Z0-9._]{3,}$/.test(u))
                        .filter((value, index, self) => self.indexOf(value) === index);
                """)
                new_height = driver.execute_script("return document.querySelector('div[role=\"dialog\"].x1ja2u2z').scrollHeight")
                if new_height == last_height or len(usernames) >= self.limit:
                    break
                last_height = new_height
                attempt += 1

            if not usernames:
                self.log_signal.emit(f"No valid {list_type} found.", "error")
                self.notification_signal.emit(f"No valid {list_type} found for {target_username}.", "error")
                return

            self.log_signal.emit(f"Found {len(usernames)} {list_type}. Starting {self.action} process...", "success")
            self.progress_signal.emit(0)
            successful_actions = []
            failed_actions = []
            max_actions = min(len(usernames), self.limit)
            csv_file = f"E:/DOWNLOADS/InstagramBotPython/{self.action}_log.csv"

            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if os.stat(csv_file).st_size == 0:
                    writer.writerow(["Timestamp", "Username", "Action", "Status"])

            for i, username in enumerate(usernames[:max_actions], 1):
                if not self.running:
                    return
                self.status_signal.emit(f"{self.action.capitalize()}ing {username} ({i}/{max_actions})...")
                self.log_signal.emit(f"{self.action.capitalize()}ing {username} ({i}/{max_actions})...", "info")
                driver.get(f"https://www.instagram.com/{username}/")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(random.uniform(2, 4))

                try:
                    if self.action == "follow":
                        follow_button = None
                        selectors = [
                            "button._aswp",
                            "//button[contains(text(), 'Follow') and not(contains(text(), 'Following'))]",
                            "div._ap3a"
                        ]
                        for selector in selectors:
                            try:
                                follow_button = WebDriverWait(driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR if ('.' in selector or '[' not in selector) else By.XPATH, selector))
                                )
                                break
                            except:
                                continue

                        if not follow_button:
                            raise Exception("No valid Follow button found")

                        button_text = follow_button.text.lower()
                        if "follow" in button_text:
                            follow_button.click()
                            time.sleep(random.uniform(1, 2))
                            try:
                                WebDriverWait(driver, 15).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "button._aswp._aswr"))
                                )
                                self.log_signal.emit(f"Followed {username} successfully", "success")
                                self.notification_signal.emit(f"Followed {username} successfully", "success")
                                successful_actions.append(username)
                                status = "Success"
                            except:
                                # Fallback: Refresh page and check if "Follow" button is gone
                                driver.refresh()
                                time.sleep(random.uniform(2, 4))
                                try:
                                    driver.find_element(By.XPATH, "//button[contains(text(), 'Follow') and not(contains(text(), 'Following'))]")
                                    raise Exception("Follow action not confirmed after refresh")
                                except:
                                    self.log_signal.emit(f"Followed {username} successfully", "success")
                                    self.notification_signal.emit(f"Followed {username} successfully", "success")
                                    successful_actions.append(username)
                                    status = "Success"
                        else:
                            self.log_signal.emit(f"Skipped {username} (already followed)", "info")
                            failed_actions.append(username)
                            status = "Skipped"
                    else:  # unfollow
                        following_button = None
                        following_selectors = [
                            "button._aswp._aswr._aswv._asw_._asx2",
                            "//button[contains(text(), 'Following')]"
                        ]
                        for selector in following_selectors:
                            try:
                                following_button = WebDriverWait(driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR if '.' in selector else By.XPATH, selector))
                                )
                                break
                            except:
                                continue

                        if not following_button:
                            raise Exception("No valid Following button found")

                        following_button.click()
                        time.sleep(random.uniform(3, 5))

                        try:
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog'].x1ja2u2z"))
                            )
                            self.log_signal.emit("Opened dialog box for Unfollow", "info")
                        except:
                            raise Exception("Dialog box for Unfollow not found")

                        unfollow_button = None
                        unfollow_selectors = [
                            "div[role='dialog'] button._a9--._ap36._a9_1",
                            "div[role='dialog'] span.x1lliihq.x193iq5w.x1ji0vk5.x18bv5gf",
                            "div[role='dialog'] span.x1lliihq.x193iq5w",
                            "div[role='dialog'] button[contains(text(), 'Unfollow')]",
                            "div[role='dialog'] div._a9-v div._a9-w button"
                        ]
                        for selector in unfollow_selectors:
                            try:
                                unfollow_button = WebDriverWait(driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR if selector.startswith("div") else By.XPATH, selector))
                                )
                                button_text = unfollow_button.text.lower().strip()
                                if "unfollow" in button_text:
                                    break
                                unfollow_button = None
                            except:
                                continue

                        if not unfollow_button:
                            unfollow_button = driver.execute_script("""
                                let elements = document.querySelectorAll('div[role="dialog"] span, div[role="dialog"] button');
                                for (let el of elements) {
                                    if (el.textContent.trim().toLowerCase() === 'unfollow') {
                                        return el;
                                    }
                                }
                                return null;
                            """)
                            if not unfollow_button:
                                raise Exception("No valid Unfollow button found")

                        unfollow_button.click()
                        time.sleep(random.uniform(3, 5))

                        # Confirm unfollow with multiple checks
                        try:
                            WebDriverWait(driver, 15).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "button._aswp"))
                            )
                            self.log_signal.emit(f"Unfollowed {username} successfully", "success")
                            self.notification_signal.emit(f"Unfollowed {username} successfully", "success")
                            successful_actions.append(username)
                            status = "Success"
                        except:
                            # Fallback: Refresh page and check if "Following" button is gone
                            driver.refresh()
                            time.sleep(random.uniform(2, 4))
                            try:
                                driver.find_element(By.XPATH, "//button[contains(text(), 'Following')]")
                                raise Exception("Unfollow action not confirmed after refresh")
                            except:
                                self.log_signal.emit(f"Unfollowed {username} successfully", "success")
                                self.notification_signal.emit(f"Unfollowed {username} successfully", "success")
                                successful_actions.append(username)
                                status = "Success"
                except Exception as e:
                    self.log_signal.emit(f"Could not {self.action} {username}: {str(e)}", "error")
                    self.notification_signal.emit(f"Failed to {self.action} {username}", "error")
                    failed_actions.append(username)
                    status = "Failed"

                with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), username, self.action.capitalize(), status])

                self.progress_signal.emit(i)
                self.summary_signal.emit(len(successful_actions), len(failed_actions), max_actions, self.action)
                time.sleep(random.uniform(20, 30))

                if i % 5 == 0:
                    pause_time = random.uniform(120, 300)
                    self.log_signal.emit(f"Pausing for {pause_time/60:.1f} minutes after {i} {self.action}s...", "info")
                    for _ in range(int(pause_time)):
                        if not self.running:
                            return
                        time.sleep(1)

            self.log_signal.emit(f"{self.action.capitalize()} bot finished! Summary: {len(successful_actions)} {self.action}s successful, {len(failed_actions)} failed.", "success")
            self.notification_signal.emit(f"{self.action.capitalize()} bot finished! {len(successful_actions)} {self.action}s", "success")
            if successful_actions:
                self.log_signal.emit(f"Successful {self.action}s: {', '.join(successful_actions)}", "success")
            if failed_actions:
                self.log_signal.emit(f"Failed {self.action}s: {', '.join(failed_actions)}", "error")
            self.status_signal.emit(f"{self.action.capitalize()} bot finished")
            self.summary_signal.emit(len(successful_actions), len(failed_actions), max_actions, self.action)
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

class FollowUnfollowWindow(QMainWindow):
    def __init__(self, is_dark_mode, cookie_file, username, password):
        super().__init__()
        self.setWindowTitle("Follow/Unfollow")
        self.setGeometry(200, 200, 600, 400)
        self.is_dark_mode = is_dark_mode
        self.cookie_file = cookie_file
        self.username = username
        self.password = password
        self.follow_thread = None
        self.unfollow_thread = None
        self.settings_file = "E:/DOWNLOADS/InstagramBotPython/follow_unfollow_settings.pkl"

        # UI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout()

        # Header
        self.header_label = QLabel("Follow/Unfollow Instagram Users")
        self.header_label.setFont(QFont("Arial", 20, QFont.Bold))
        self.header_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header_label)

        # Input Fields
        self.input_card = QWidget()
        self.input_layout = QGridLayout()
        self.input_layout.setSpacing(8)

        self.follow_target_input = QLineEdit()
        self.follow_target_input.setPlaceholderText("Target Username to Follow (e.g., @username)")
        self.input_layout.addWidget(QLabel("Follow Target Username:"), 0, 0)
        self.input_layout.addWidget(self.follow_target_input, 0, 1)

        self.follow_limit_input = QLineEdit()
        self.follow_limit_input.setPlaceholderText("Follow Limit (10-100)")
        self.input_layout.addWidget(QLabel("Follow Limit:"), 1, 0)
        self.input_layout.addWidget(self.follow_limit_input, 1, 1)

        self.unfollow_target_input = QLineEdit()
        self.unfollow_target_input.setPlaceholderText("Your Username for Unfollow (e.g., @username)")
        self.input_layout.addWidget(QLabel("Unfollow Target Username:"), 2, 0)
        self.input_layout.addWidget(self.unfollow_target_input, 2, 1)

        self.unfollow_limit_input = QLineEdit()
        self.unfollow_limit_input.setPlaceholderText("Unfollow Limit (10-100)")
        self.input_layout.addWidget(QLabel("Unfollow Limit:"), 3, 0)
        self.input_layout.addWidget(self.unfollow_limit_input, 3, 1)

        self.input_card.setLayout(self.input_layout)
        self.main_layout.addWidget(self.input_card)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.follow_button = QPushButton("Start Follow")
        self.follow_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/play1_icon.png"))
        self.follow_button.setFixedSize(120, 35)
        self.follow_button.clicked.connect(self.start_follow)
        self.button_layout.addWidget(self.follow_button)

        self.unfollow_button = QPushButton("Start Unfollow")
        self.unfollow_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/play_icon.png"))
        self.unfollow_button.setFixedSize(120, 35)
        self.unfollow_button.clicked.connect(self.start_unfollow)
        self.button_layout.addWidget(self.unfollow_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/stop_icon.png"))
        self.stop_button.setFixedSize(120, 35)
        self.stop_button.clicked.connect(self.stop_action)
        self.stop_button.setEnabled(False)
        self.button_layout.addWidget(self.stop_button)

        self.clear_logs_button = QPushButton("Clear Logs")
        self.clear_logs_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/clear_icon.png"))
        self.clear_logs_button.setFixedSize(120, 35)
        self.clear_logs_button.clicked.connect(self.clear_logs)
        self.button_layout.addWidget(self.clear_logs_button)

        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/save_icon.png"))
        self.save_settings_button.setFixedSize(120, 35)
        self.save_settings_button.clicked.connect(self.save_settings)
        self.button_layout.addWidget(self.save_settings_button)

        self.main_layout.addLayout(self.button_layout)

        # Summary Label
        self.summary_label = QLabel("Followed: 0 | Failed: 0 | Remaining: 0\nUnfollowed: 0 | Failed: 0 | Remaining: 0")
        self.main_layout.addWidget(self.summary_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.main_layout.addWidget(self.progress_bar)

        # Log Box
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(150)  # Limiting height to balance UI
        self.main_layout.addWidget(self.logs)

        # User Guide Box
        self.user_guide = QTextEdit()
        self.user_guide.setReadOnly(True)
        self.user_guide.setStyleSheet(self.get_input_style())
        self.user_guide.setFixedHeight(150)  # Adjust height for content
        self.user_guide.setHtml("""
            <h2 style='color: #2196F3;'>User Guide</h2>
            <p><b>Follow these steps to use the Follow/Unfollow Bot effectively:</b></p>
            <ul>
                <li><span style='color: #4CAF50;'>✅</span> <b>Follow Target Username</b>: Enter the Instagram username (e.g., @username) whose followers you want to follow.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Follow Limit</b>: Set a daily follow limit between 10 and 100 to avoid Instagram restrictions.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Unfollow Target Username</b>: Enter your Instagram username (e.g., @yourusername) to unfollow users you are following.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Unfollow Limit</b>: Set a daily unfollow limit between 10 and 100 to avoid restrictions.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Start Follow Button</b>: Click to start following users from the target account's followers list.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Start Unfollow Button</b>: Click to start unfollowing users from your following list.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Stop Button</b>: Click to stop the bot if needed.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Clear Logs Button</b>: Click to clear the activity log.</li>
                <li><span style='color: #4CAF50;'>✅</span> <b>Save Settings Button</b>: Click to save your settings for future use.</li>
            </ul>
            <p><b>Note:</b> Ensure a stable internet connection and valid Instagram credentials (provided in the main window). Results are logged in a CSV file in the project directory.</p>
        """)
        self.main_layout.addWidget(self.user_guide)

        self.central_widget.setLayout(self.main_layout)

        # Apply initial theme
        self.apply_theme()

        # Load settings
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
        self.follow_target_input.setStyleSheet(self.get_input_style())
        self.follow_limit_input.setStyleSheet(self.get_input_style())
        self.unfollow_target_input.setStyleSheet(self.get_input_style())
        self.unfollow_limit_input.setStyleSheet(self.get_input_style())
        self.follow_button.setStyleSheet(self.get_button_style())
        self.unfollow_button.setStyleSheet(self.get_button_style())
        self.stop_button.setStyleSheet(self.get_button_style())
        self.clear_logs_button.setStyleSheet(self.get_button_style())
        self.save_settings_button.setStyleSheet(self.get_button_style())
        self.summary_label.setStyleSheet(self.get_label_style())
        self.progress_bar.setStyleSheet(self.get_progress_style())
        self.logs.setStyleSheet(self.get_input_style())
        self.user_guide.setStyleSheet(self.get_input_style())  # Apply style to user guide
        self.header_label.setStyleSheet(self.get_label_style())

    def log(self, message, message_type="info"):
        color = {"info": "#000000" if not self.is_dark_mode else "#FFFFFF",
                 "success": "#4CAF50",
                 "error": "#F44336"}.get(message_type, "#000000" if not self.is_dark_mode else "#FFFFFF")
        self.logs.append(f'<span style="color: {color}; font-family: Arial;">[{time.strftime("%H:%M:%S")}] {message}</span>')
        self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())

    def show_notification(self, message, message_type):
        msg = QMessageBox()
        msg.setWindowTitle("Notification")
        msg.setText(message)
        msg.setStyleSheet(self.get_notification_style())
        msg.exec_()

    def update_summary(self, successful, failed, total, action):
        if action == "follow":
            self.summary_label.setText(f"Followed: {successful} | Failed: {failed} | Remaining: {total - successful - failed}\nUnfollowed: 0 | Failed: 0 | Remaining: 0")
        else:
            self.summary_label.setText(f"Followed: 0 | Failed: 0 | Remaining: 0\nUnfollowed: {successful} | Failed: {failed} | Remaining: {total - successful - failed}")

    def start_follow(self):
        if self.follow_thread and self.follow_thread.isRunning():
            self.log("Follow bot is already running!", "error")
            self.show_notification("Follow bot is already running!", "error")
            return

        target_username = self.follow_target_input.text().strip().replace('@', '')
        try:
            limit = int(self.follow_limit_input.text())
            if limit < 10 or limit > 100:
                raise ValueError
        except ValueError:
            self.log("Please enter a valid follow limit (10-100)!", "error")
            self.show_notification("Invalid follow limit!", "error")
            return

        if not self.username or not self.password:
            self.log("Please enter Instagram username and password in the main window!", "error")
            self.show_notification("Instagram username or password missing!", "error")
            return

        if not target_username:
            self.log("Please enter a target username for follow!", "error")
            self.show_notification("Target username is empty!", "error")
            return

        self.follow_thread = FollowUnfollowThread(self.username, self.password, self.cookie_file, target_username, "follow", limit)
        self.follow_thread.log_signal.connect(self.log)
        self.follow_thread.progress_signal.connect(self.progress_bar.setValue)
        self.follow_thread.status_signal.connect(self.statusBar().showMessage)
        self.follow_thread.summary_signal.connect(self.update_summary)
        self.follow_thread.notification_signal.connect(self.show_notification)
        self.follow_thread.finished_signal.connect(self.action_finished)
        self.follow_thread.start()

        self.follow_button.setEnabled(False)
        self.unfollow_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log("Starting follow bot...", "info")
        self.show_notification("Starting follow bot...", "info")
        self.summary_label.setText("Followed: 0 | Failed: 0 | Remaining: 0\nUnfollowed: 0 | Failed: 0 | Remaining: 0")

    def start_unfollow(self):
        if self.unfollow_thread and self.unfollow_thread.isRunning():
            self.log("Unfollow bot is already running!", "error")
            self.show_notification("Unfollow bot is already running!", "error")
            return

        target_username = self.unfollow_target_input.text().strip().replace('@', '')
        try:
            limit = int(self.unfollow_limit_input.text())
            if limit < 10 or limit > 100:
                raise ValueError
        except ValueError:
            self.log("Please enter a valid unfollow limit (10-100)!", "error")
            self.show_notification("Invalid unfollow limit!", "error")
            return

        if not self.username or not self.password:
            self.log("Please enter Instagram username and password in the main window!", "error")
            self.show_notification("Instagram username or password missing!", "error")
            return

        if not target_username:
            self.log("Please enter a target username for unfollow!", "error")
            self.show_notification("Target username is empty!", "error")
            return

        self.unfollow_thread = FollowUnfollowThread(self.username, self.password, self.cookie_file, target_username, "unfollow", limit)
        self.unfollow_thread.log_signal.connect(self.log)
        self.unfollow_thread.progress_signal.connect(self.progress_bar.setValue)
        self.unfollow_thread.status_signal.connect(self.statusBar().showMessage)
        self.unfollow_thread.summary_signal.connect(self.update_summary)
        self.unfollow_thread.notification_signal.connect(self.show_notification)
        self.unfollow_thread.finished_signal.connect(self.action_finished)
        self.unfollow_thread.start()

        self.follow_button.setEnabled(False)
        self.unfollow_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log("Starting unfollow bot...", "info")
        self.show_notification("Starting unfollow bot...", "info")
        self.summary_label.setText("Followed: 0 | Failed: 0 | Remaining: 0\nUnfollowed: 0 | Failed: 0 | Remaining: 0")

    def stop_action(self):
        if self.follow_thread and self.follow_thread.isRunning():
            self.follow_thread.running = False
            self.follow_thread.wait()
            self.log("Follow bot stopped by user", "error")
            self.show_notification("Follow bot stopped by user", "error")
        if self.unfollow_thread and self.unfollow_thread.isRunning():
            self.unfollow_thread.running = False
            self.unfollow_thread.wait()
            self.log("Unfollow bot stopped by user", "error")
            self.show_notification("Unfollow bot stopped by user", "error")
        self.follow_button.setEnabled(True)
        self.unfollow_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("Ready")

    def action_finished(self):
        self.follow_button.setEnabled(True)
        self.unfollow_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("Ready")
        self.follow_thread = None
        self.unfollow_thread = None

    def clear_logs(self):
        self.logs.clear()
        self.log("Logs cleared", "success")
        self.show_notification("Logs cleared", "success")

    def save_settings(self):
        settings = {
            "follow_target": self.follow_target_input.text(),
            "follow_limit": self.follow_limit_input.text(),
            "unfollow_target": self.unfollow_target_input.text(),
            "unfollow_limit": self.unfollow_limit_input.text()
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
                self.follow_target_input.setText(settings.get("follow_target", ""))
                self.follow_limit_input.setText(settings.get("follow_limit", ""))
                self.unfollow_target_input.setText(settings.get("unfollow_target", ""))
                self.unfollow_limit_input.setText(settings.get("unfollow_limit", ""))
                self.log("Settings loaded successfully", "success")
            except Exception as e:
                self.log(f"Error loading settings: {str(e)}", "error")