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
        response = requests.get('https://raw.githubusercontent.com/rudi2005/InstagramDMBot-New/main/control.txt')
        if response.status_code == 200:
            status = response.text.strip().lower()
            if status == 'inactive':
                print("Bot is disabled (control.txt is set to 'inactive'). Exiting...")
                sys.exit(0)
            elif status == 'active':
                print("Bot is enabled (control.txt is set to 'active'). Starting...")
            else:
                print("Invalid control.txt content. Expected 'active' or 'inactive'. Exiting...")
                sys.exit(1)
        else:
            print("Failed to fetch control.txt. Exiting...")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking control.txt: {e}. Exiting...")
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
904                if not self.running:
905                    return
906                self.status_signal.emit(f"Sending DM to {commenter} ({i}/{max_dms})...")
907                self.log_signal.emit(f"Sending DM to {commenter} ({i}/{max_dms})...", "info")
908                driver.get(f"https://www.instagram.com/{commenter}")
909                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
910                time.sleep(random.uniform(2, 4))
911
912                try:
913                    message_button = WebDriverWait(driver, 5).until(
914                        EC.element_to_be_clickable((By.XPATH, "//div[text()='Message']"))
915                    )
916                    message_button.click()
917                except:
918                    try:
919                        driver.find_element(By.XPATH, "//svg[@aria-label='Options']").click()
920                        WebDriverWait(driver, 5).until(
921                            EC.element_to_be_clickable((By.XPATH, "//button[text()='Send message']"))
922                        ).click()
923                    except:
924                        self.log_signal.emit(f"Could not find Message button for {commenter}. It might be a private account. Skipping...", "error")
925                        self.notification_signal.emit(f"Failed to DM {commenter}", "error")
926                        failed_dms.append(commenter)
927                        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
928                            writer = csv.writer(f)
929                            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Failed"])
930                        self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
931                        self.stats_signal.emit(successful_dms, failed_dms)
932                        continue
933
934                try:
935                    textarea = WebDriverWait(driver, 10).until(
936                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='Message']"))
937                    )
938                    textarea.click()
939                    message = random.choice(self.messages)
940                    if not self.type_like_human(textarea, message):
941                        return
942                    self.log_signal.emit(f"Typed message for {commenter}", "success")
943                except:
944                    self.log_signal.emit(f"Could not find or type in Message box for {commenter}. Skipping...", "error")
945                    self.notification_signal.emit(f"Failed to DM {commenter}", "error")
946                    failed_dms.append(commenter)
947                    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
948                        writer = csv.writer(f)
949                        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Failed"])
950                    self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
951                    self.stats_signal.emit(successful_dms, failed_dms)
952                    continue
953
954                try:
955                    send_button = WebDriverWait(driver, 5).until(
956                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='Send']"))
957                    )
958                    send_button.click()
959                    self.log_signal.emit(f"DM sent to {commenter}", "success")
960                    self.notification_signal.emit(f"DM sent to {commenter}", "success")
961                    successful_dms.append(commenter)
962                    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
963                        writer = csv.writer(f)
964                        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Success"])
965                except:
966                    self.log_signal.emit(f"Could not find Send button for {commenter}. Skipping...", "error")
967                    self.notification_signal.emit(f"Failed to DM {commenter}", "error")
968                    failed_dms.append(commenter)
969                    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
970                        writer = csv.writer(f)
971                        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), commenter, "DM", "Failed"])
972                    self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
973                    self.stats_signal.emit(successful_dms, failed_dms)
974                    continue
975
976                self.progress_signal.emit(i)
977                self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
978                self.stats_signal.emit(successful_dms, failed_dms)
979                time.sleep(random.uniform(10, 20))
980
981                if i % 5 == 0:
982                    pause_time = random.uniform(120, 300)
983                    self.log_signal.emit(f"Pausing for {pause_time/60:.1f} minutes after {i} DMs...", "info")
984                    for _ in range(int(pause_time)):
985                        if not self.running:
986                            return
987                        time.sleep(1)
988
989            self.log_signal.emit(f"Bot finished! Summary: {len(successful_dms)} DMs sent successfully, {len(failed_dms)} failed.", "success")
990            self.notification_signal.emit(f"Bot finished! {len(successful_dms)} DMs sent", "success")
991            if successful_dms:
992                self.log_signal.emit(f"Successful DMs: {', '.join(successful_dms)}", "success")
993            if failed_dms:
994                self.log_signal.emit(f"Failed DMs: {', '.join(failed_dms)}", "error")
995            self.status_signal.emit("Bot finished")
996            self.summary_signal.emit(len(successful_dms), len(failed_dms), max_dms)
997            self.stats_signal.emit(successful_dms, failed_dms)
998            self.finished_signal.emit()
999
1000        finally:
1001            self.save_cookies(driver)
1002            self.log_signal.emit("Closing browser...", "info")
1003            self.status_signal.emit("Closing browser...")
1004            time.sleep(2)
1005            driver.quit()
1006
1007    def type_like_human(self, element, text):
1008        for char in text:
1009            if not self.running:
1010                return False
1011            element.send_keys(char)
1012            time.sleep(random.uniform(0.4, 0.6))
1013        return True
1014
1015    def save_cookies(self, driver):
1016        try:
1017            with open(self.cookie_file, 'wb') as file:
1018                pickle.dump(driver.get_cookies(), file)
1019            self.log_signal.emit("Cookies saved for future logins", "success")
1020        except Exception as e:
1021            self.log_signal.emit(f"Error saving cookies: {str(e)}", "error")
1022
1023    def load_cookies(self, driver):
1024        if os.path.exists(self.cookie_file) and os.path.getsize(self.cookie_file) > 0:
1025            try:
1026                with open(self.cookie_file, 'rb') as file:
1027                    cookies = pickle.load(file)
1028                for cookie in cookies:
1029                    driver.add_cookie(cookie)
1030                self.log_signal.emit("Cookies loaded successfully", "success")
1031                return True
1032            except Exception as e:
1033                self.log_signal.emit(f"Error loading cookies: {str(e)}. Falling back to manual login.", "error")
1034                return False
1035        else:
1036            self.log_signal.emit("No valid cookie file found. Performing manual login...", "info")
1037            return False
1038
1039    def perform_manual_login(self, driver):
1040        try:
1041            username_field = WebDriverWait(driver, 10).until(
1042                EC.presence_of_element_located((By.NAME, "username"))
1043            )
1044            password_field = WebDriverWait(driver, 10).until(
1045                EC.presence_of_element_located((By.NAME, "password"))
1046            )
1047            self.type_like_human(username_field, self.username)
1048            self.type_like_human(password_field, self.password)
1049            driver.find_element(By.XPATH, "//button[@type='submit']").click()
1050            WebDriverWait(driver, 45).until(EC.url_contains("instagram.com"))
1051            time.sleep(random.uniform(2, 4))
1052            self.log_signal.emit("Manual login successful", "success")
1053        except Exception as e:
1054            self.log_signal.emit(f"Manual login failed: {str(e)}", "error")
1055            raise
1056
1057class InstagramBotApp(QMainWindow):
1058    def __init__(self):
1059        super().__init__()
1060        self.setWindowTitle("Instagram DM Bot")
1061        self.setGeometry(100, 100, 800, 600)
1062        self.cookie_file = "E:/DOWNLOADS/InstagramBotPython/instagram_cookies.pkl"
1063        self.settings_file = "E:/DOWNLOADS/InstagramBotPython/settings.pkl"
1064        self.bot_thread = None
1065        self.successful_dms = []
1066        self.failed_dms = []
1067        self.is_dark_mode = False
1068        self.reply_window = None
1069        self.follow_unfollow_window = None
1070        self.analytics_window = None
1071
1072        # UI Setup
1073        self.central_widget = QWidget()
1074        self.setCentralWidget(self.central_widget)
1075        self.main_layout = QHBoxLayout()
1076
1077        # Sidebar
1078        self.sidebar = QDockWidget()
1079        self.sidebar.setFixedWidth(200)
1080        self.sidebar.setFixedHeight(1000)
1081        self.sidebar.setFeatures(QDockWidget.NoDockWidgetFeatures)
1082        self.sidebar_content = QListWidget()
1083        self.sidebar_content.setItemDelegate(SidebarDelegate(self.sidebar_content))
1084        self.sidebar_content.setStyleSheet(self.get_sidebar_style())
1085        self.add_sidebar_items()
1086        self.sidebar_content.currentRowChanged.connect(self.switch_page)
1087        self.sidebar.setWidget(self.sidebar_content)
1088        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar)
1089
1090        # Pages
1091        self.main_page = QWidget()
1092        self.settings_page = QWidget()
1093        self.pages = [self.main_page, self.settings_page]
1094        self.current_page = 0
1095
1096        # Main Page
1097        self.main_layout_inner = QVBoxLayout()
1098        self.header_layout = QHBoxLayout()
1099        self.logo_label = QLabel()
1100        logo_path = "E:/DOWNLOADS/InstagramBotPython/logo.png"
1101        if os.path.exists(logo_path):
1102            self.logo_label.setPixmap(QPixmap(logo_path))
1103            self.logo_label.setScaledContents(True)
1104            self.logo_label.setFixedSize(150, 50)
1105        else:
1106            self.logo_label.setText("DM Bot")
1107            self.logo_label.setFont(QFont("Arial", 24, QFont.Bold))
1108        self.logo_label.setStyleSheet(self.get_logo_style())
1109        self.header_layout.addWidget(self.logo_label)
1110
1111        # Mode Switch Button
1112        self.mode_button = QPushButton()
1113        self.mode_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/mode_icon.png"))
1114        self.mode_button.setFixedSize(35, 35)
1115        self.mode_button.setStyleSheet(self.get_button_style())
1116        self.mode_button.clicked.connect(self.toggle_mode)
1117        self.header_layout.addStretch()
1118        self.header_layout.addWidget(self.mode_button)
1119        self.main_layout_inner.addLayout(self.header_layout)
1120
1121        # Input Fields
1122        self.input_card = QWidget()
1123        self.input_card.setStyleSheet(self.get_card_style())
1124        self.input_layout = QGridLayout()
1125        self.input_layout.setSpacing(8)
1126        self.username_input = QLineEdit()
1127        self.username_input.setPlaceholderText("Username")
1128        self.username_input.setStyleSheet(self.get_input_style())
1129        self.input_layout.addWidget(QLabel("Username:"), 0, 0)
1130        self.input_layout.addWidget(self.username_input, 0, 1)
1131
1132        self.password_input = QLineEdit()
1133        self.password_input.setPlaceholderText("Password")
1134        self.password_input.setEchoMode(QLineEdit.Password)
1135        self.password_input.setStyleSheet(self.get_input_style())
1136        self.input_layout.addWidget(QLabel("Password:"), 1, 0)
1137        self.input_layout.addWidget(self.password_input, 1, 1)
1138
1139        self.reel_url_input = QLineEdit()
1140        self.reel_url_input.setPlaceholderText("Reel URL")
1141        self.reel_url_input.setStyleSheet(self.get_input_style())
1142        self.input_layout.addWidget(QLabel("Reel URL:"), 2, 0)
1143        self.input_layout.addWidget(self.reel_url_input, 2, 1)
1144
1145        self.message_input = QTextEdit()
1146        self.message_input.setPlaceholderText("Messages (one per line)")
1147        self.message_input.setFixedHeight(80)
1148        self.message_input.setStyleSheet(self.get_input_style())
1149        self.input_layout.addWidget(QLabel("Messages:"), 3, 0)
1150        self.input_layout.addWidget(self.message_input, 3, 1)
1151        self.input_card.setLayout(self.input_layout)
1152        self.main_layout_inner.addWidget(self.input_card)
1153
1154        # Buttons
1155        self.button_layout = QHBoxLayout()
1156        self.save_button = QPushButton("Save")
1157        self.save_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/save_icon.png"))
1158        self.save_button.setFixedSize(100, 35)
1159        self.save_button.setStyleSheet(self.get_button_style())
1160        self.save_button.clicked.connect(self.save_settings)
1161        self.button_layout.addWidget(self.save_button)
1162
1163        self.start_button = QPushButton("Start")
1164        self.start_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/play_icon.png"))
1165        self.start_button.setFixedSize(100, 35)
1166        self.start_button.setStyleSheet(self.get_button_style())
1167        self.start_button.clicked.connect(self.start_bot)
1168        self.button_layout.addWidget(self.start_button)
1169
1170        self.stop_button = QPushButton("Stop")
1171        self.stop_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/stop_icon.png"))
1172        self.stop_button.setFixedSize(100, 35)
1173        self.stop_button.setStyleSheet(self.get_button_style())
1174        self.stop_button.clicked.connect(self.stop_bot)
1175        self.stop_button.setEnabled(False)
1176        self.button_layout.addWidget(self.stop_button)
1177
1178        self.clear_logs_button = QPushButton("Clear")
1179        self.clear_logs_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/clear_icon.png"))
1180        self.clear_logs_button.setFixedSize(100, 35)
1181        self.clear_logs_button.setStyleSheet(self.get_button_style())
1182        self.clear_logs_button.clicked.connect(self.clear_logs)
1183        self.button_layout.addWidget(self.clear_logs_button)
1184        self.main_layout_inner.addLayout(self.button_layout)
1185
1186        # DM Summary Label
1187        self.summary_label = QLabel("DMs Sent: 0 | Failed: 0 | Remaining: 0")
1188        self.summary_label.setStyleSheet(self.get_label_style())
1189        self.main_layout_inner.addWidget(self.summary_label)
1190
1191        # Progress Bar
1192        self.progress_bar = QProgressBar()
1193        self.progress_bar.setStyleSheet(self.get_progress_style())
1194        self.progress_bar.setValue(0)
1195        self.main_layout_inner.addWidget(self.progress_bar)
1196
1197        # Activity Log Box
1198        self.logs = QTextEdit()
1199        self.logs.setReadOnly(True)
1200        self.logs.setStyleSheet(self.get_input_style())
1201        self.logs.setFixedHeight(150)
1202        self.main_layout_inner.addWidget(self.logs)
1203
1204        # User Guide Box
1205        self.user_guide = QTextEdit()
1206        self.user_guide.setReadOnly(True)
1207        self.user_guide.setStyleSheet(self.get_input_style())
1208        self.user_guide.setFixedHeight(200)
1209        self.user_guide.setHtml("""
1210            <h2 style='color: #2196F3;'>User Guide</h2>
1211            <p><b>Follow these steps to use the Instagram DM Bot effectively:</b></p>
1212            <ul>
1213                <li><span style='color: #4CAF50;'>✅</span> <b>Username</b>: Enter your Instagram username (e.g., <i>your_username</i>) without the '@' symbol.</li>
1214                <li><span style='color: #4CAF50;'>✅</span> <b>Password</b>: Enter your Instagram account password. Ensure it is correct and keep it secure.</li>
1215                <li><span style='color: #4CAF50;'>✅</span> <b>Reel URL</b>: Copy the full URL of an Instagram reel (e.g., <i>https://www.instagram.com/reel/ABC123/</i>) from the browser or app. The bot will extract commenters from this reel.</li>
1216                <li><span style='color: #4CAF50;'>✅</span> <b>Messages</b>: Write one or more messages, each on a new line. The bot will randomly select one message to send to each commenter (e.g., <i>Hello! Thanks for your comment!</i>).</li>
1217                <li><span style='color: #4CAF50;'>✅</span> <b>DM Limit</b>: Set a daily DM limit between 10 and 200 in the Settings page to avoid Instagram restrictions.</li>
1218                <li><span style='color: #4CAF50;'>✅</span> <b>Save Button</b>: Click to save your inputs for future use.</li>
1219                <li><span style='color: #4CAF50;'>✅</span> <b>Start Button</b>: Click to begin sending DMs to reel commenters.</li>
1220                <li><span style='color: #4CAF50;'>✅</span> <b>Scrolling Manually</b>: Ensure Scroll Manually Use (Mouse & Trackpad) Loading All Comments.</li>                
1221                <li><span style='color: #4CAF50;'>✅</span> <b>Stop Button</b>: Click to stop the bot if needed.</li>
1222                <li><span style='color: #4CAF50;'>✅</span> <b>Clear Button</b>: Click to clear the activity log.</li>
1223            </ul>
1224            <p><b>Note:</b> Ensure a stable internet connection and valid Instagram credentials to avoid errors.</p>
1225        """)
1226        self.main_layout_inner.addWidget(self.user_guide)
1227
1228        self.main_page.setLayout(self.main_layout_inner)
1229
1230        # Settings Page
1231        self.settings_layout = QVBoxLayout()
1232        self.dm_limit_label = QLabel("Daily DM Limit:")
1233        self.dm_limit_label.setStyleSheet(self.get_label_style())
1234        self.settings_layout.addWidget(self.dm_limit_label)
1235
1236        self.dm_limit_input = QLineEdit()
1237        self.dm_limit_input.setPlaceholderText("Enter DM Limit (10-200)")
1238        self.dm_limit_input.setStyleSheet(self.get_input_style())
1239        self.settings_layout.addWidget(self.dm_limit_input)
1240
1241        self.password_settings_input = QLineEdit()
1242        self.password_settings_input.setPlaceholderText("Password")
1243        self.password_settings_input.setEchoMode(QLineEdit.Password)
1244        self.password_settings_input.setStyleSheet(self.get_input_style())
1245        self.settings_layout.addWidget(QLabel("Password:"))
1246        self.settings_layout.addWidget(self.password_settings_input)
1247
1248        self.save_settings_button = QPushButton("Save")
1249        self.save_settings_button.setIcon(QIcon("E:/DOWNLOADS/InstagramBotPython/icons/save_icon.png"))
1250        self.save_settings_button.setFixedSize(100, 35)
1251        self.save_settings_button.setStyleSheet(self.get_button_style())
1252        self.save_settings_button.clicked.connect(self.save_settings)
1253        self.settings_layout.addWidget(self.save_settings_button)
1254        self.settings_layout.addStretch()
1255        self.settings_page.setLayout(self.settings_layout)
1256
1257        # Add main page to layout
1258        self.main_layout.addWidget(self.main_page)
1259        self.central_widget.setLayout(self.main_layout)
1260
1261        # Status Bar
1262        self.statusBar = QStatusBar()
1263        self.setStatusBar(self.statusBar)
1264        self.statusBar.showMessage("Ready")
1265        self.statusBar.setStyleSheet(self.get_label_style())
1266
1267        # Apply initial theme
1268        self.apply_theme()
1269
1270        # Load settings
1271        self.load_settings()
1272
1273    def add_sidebar_items(self):
1274        items = [
1275            ("Main", "main_icon.png"),
1276            ("Settings", "settings_icon.png"),
1277            ("Analytics", "analytics_icon.png"),
1278            ("Reply DMs", "reply_icon.png"),
1279            ("Follow/Unfollow", "follow_icon.png"),
1280            ("COMING SOON", "coming_soon.png"),
1281            ("Schedule Posts", "schedule_icon.png"),
1282            ("Auto Like", "like_icon.png"),
1283            ("Comment Bot", "comment_icon.png"),
1284            ("Profile Analytics", "profile_icon.png"),
1285            ("Hashtag Generator", "hashtag_icon.png"),
1286            ("Loginsta™ © 2025.", "powered_by_icon.png")
1287        ]
1288        for text, icon in items:
1289            item = QListWidgetItem()
1290            item.setText(text)
1291            if icon:
1292                item.setIcon(QIcon(f"E:/DOWNLOADS/InstagramBotPython/icons/{icon}"))
1293            if text == "COMING SOON FEATURES NEXT UPDATE":
1294                item.setData(Qt.UserRole, "coming_soon")
1295            self.sidebar_content.addItem(item)
1296
1297    def get_sidebar_style(self):
1298        if self.is_dark_mode:
1299            return """
1300                QListWidget {
1301                    background: #263238;
1302                    border: 1px solid #B0BEC5;
1303                    font-family: Arial;
1304                    font-size: 16px;
1305                    font-weight: bold;
1306                    color: #FFFFFF;
1307                    border-radius: 5px;
1308                }
1309                QListWidget::item {
1310                    padding: 8px;
1311                    border: none;
1312                    font-weight: bold;
1313                }
1314                QListWidget::item:selected {
1315                    background: #37474F;
1316                    color: #FFFFFF;
1317                    font-weight: bold;
1318                    border-radius: 5px;
1319                }
1320                QListWidget::item:hover {
1321                    background: #455A64;
1322                    font-weight: bold;
1323                    border-radius: 5px;
1324                }
1325            """
1326        else:
1327            return """
1328                QListWidget {
1329                    background: #FFFFFF;
1330                    border: 1px solid #B0BEC5;
1331                    font-family: Arial;
1332                    font-size: 16px;
1333                    font-weight: bold;
1334                    color: #000000;
1335                    border-radius: 5px;
1336                }
1337                QListWidget::item {
1338                    padding: 8px;
1339                    border: none;
1340                    font-weight: bold;
1341                }
1342                QListWidget::item:selected {
1343                    background: #E3F2FD;
1344                    color: #000000;
1345                    font-weight: bold;
1346                    border-radius: 5px;
1347                }
1348                QListWidget::item:hover {
1349                    background: #F5F7FA;
1350                    font-weight: bold;
1351                    border-radius: 5px;
1352                }
1353            """
1354
1355    def get_card_style(self):
1356        if self.is_dark_mode:
1357            return """
1358                QWidget {
1359                    background: #37474F;
1360                    border: 1px solid #B0BEC5;
1361                    border-radius: 5px;
1362                    padding: 10px;
1363                }
1364            """
1365        else:
1366            return """
1367                QWidget {
1368                    background: #FFFFFF;
1369                    border: 1px solid #B0BEC5;
1370                    border-radius: 5px;
1371                    padding: 10px;
1372                }
1373            """
1374
1375    def get_input_style(self):
1376        if self.is_dark_mode:
1377            return """
1378                QLineEdit, QTextEdit {
1379                    padding: 8px;
1380                    border: 1px solid #B0BEC5;
1381                    border-radius: 5px;
1382                    background: #455A64;
1383                    color: #FFFFFF;
1384                    font-family: Arial;
1385                    font-size: 16px;
1386                }
1387                QLineEdit:focus, QTextEdit:focus {
1388                    border: 1px solid #4FC3F7;
1389                    background: #546E7A;
1390                }
1391            """
1392        else:
1393            return """
1394                QLineEdit, QTextEdit {
1395                    padding: 8px;
1396                    border: 1px solid #B0BEC5;
1397                    border-radius: 5px;
1398                    background: #FFFFFF;
1399                    color: #000000;
1400                    font-family: Arial;
1401                    font-size: 16px;
1402                }
1403                QLineEdit:focus, QTextEdit:focus {
1404                    border: 1px solid #2196F3;
1405                    background: #F5F7FA;
1406                }
1407            """
1408
1409    def get_button_style(self):
1410        if self.is_dark_mode:
1411            return """
1412                QPushButton {
1413                    background: transparent;
1414                    color: #FFFFFF;
1415                    padding: 6px;
1416                    border-radius: 5px;
1417                    font-family: Arial;
1418                    font-size: 16px;
1419                    border: 1px solid #B0BEC5;
1420                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
1421                }
1422                QPushButton:hover {
1423                    background: #4FC3F7;
1424                    border: 1px solid #4FC3F7;
1425                    color: #000000;
1426                }
1427            """
1428        else:
1429            return """
1430                QPushButton {
1431                    background: transparent;
1432                    color: #000000;
1433                    padding: 6px;
1434                    border-radius: 5px;
1435                    font-family: Arial;
1436                    font-size: 16px;
1437                    border: 1px solid #B0BEC5;
1438                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
1439                }
1440                QPushButton:hover {
1441                    background: #2196F3;
1442                    border: 1px solid #2196F3;
1443                    color: #FFFFFF;
1444                }
1445            """
1446
1447    def get_label_style(self):
1448        if self.is_dark_mode:
1449            return """
1450                QLabel, QStatusBar {
1451                    color: #FFFFFF;
1452                    font-family: Arial;
1453                    font-size: 16px;
1454                    background: #263238;
1455                    border-radius: 5px;
1456                    padding: 6px;
1457                }
1458            """
1459        else:
1460            return """
1461                QLabel, QStatusBar {
1462                    color: #000000;
1463                    font-family: Arial;
1464                    font-size: 16px;
1465                    background: #FFFFFF;
1466                    border-radius: 5px;
1467                    padding: 6px;
1468                }
1469            """
1470
1471    def get_progress_style(self):
1472        if self.is_dark_mode:
1473            return """
1474                QProgressBar {
1475                    border: 1px solid #B0BEC5;
1476                    border-radius: 5px;
1477                    background: #455A64;
1478                    text-align: center;
1479                    color: #FFFFFF;
1480                    font-family: Arial;
1481                    font-size: 16px;
1482                }
1483                QProgressBar::chunk {
1484                    background: #4FC3F7;
1485                    border-radius: 5px;
1486                }
1487            """
1488        else:
1489            return """
1490                QProgressBar {
1491                    border: 1px solid #B0BEC5;
1492                    border-radius: 5px;
1493                    background: #FFFFFF;
1494                    text-align: center;
1495                    color: #000000;
1496                    font-family: Arial;
1497                    font-size: 16px;
1498                }
1499                QProgressBar::chunk {
1500                    background: #2196F3;
1501                    border-radius: 5px;
1502                }
1503            """
1504
1505    def get_logo_style(self):
1506        if self.is_dark_mode:
1507            return """
1508                QLabel {
1509                    color: #FFFFFF;
1510                    font-family: Arial;
1511                    font-size: 24px;
1512                    background: #263238;
1513                    border: 1px solid #B0BEC5;
1514                    border-radius: 5px;
1515                    padding: 8px;
1516                }
1517            """
1518        else:
1519            return """
1520                QLabel {
1521                    color: #000000;
1522                    font-family: Arial;
1523                    font-size: 24px;
1524                    background: #FFFFFF;
1525                    border: 1px solid #B0BEC5;
1526                    border-radius: 5px;
1527                    padding: 8px;
1528                }
1529            """
1530
1531    def get_notification_style(self):
1532        if self.is_dark_mode:
1533            return """
1534                QMessageBox {
1535                    background: #37474F;
1536                    color: #FFFFFF;
1537                    font-family: Arial;
1538                    font-size: 16px;
1539                    border: 1px solid #B0BEC5;
1540                    border-radius: 5px;
1541                }
1542                QMessageBox QPushButton {
1543                    background: transparent;
1544                    color: #FFFFFF;
1545                    padding: 6px;
1546                    border-radius: 5px;
1547                    font-family: Arial;
1548                    font-size: 16px;
1549                    border: 1px solid #B0BEC5;
1550                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
1551                }
1552                QMessageBox QPushButton:hover {
1553                    background: #4FC3F7;
1554                    border: 1px solid #4FC3F7;
1555                    color: #000000;
1556                }
1557            """
1558        else:
1559            return """
1560                QMessageBox {
1561                    background: #FFFFFF;
1562                    color: #000000;
1563                    font-family: Arial;
1564                    font-size: 16px;
1565                    border: 1px solid #B0BEC5;
1566                    border-radius: 5px;
1567                }
1568                QMessageBox QPushButton {
1569                    background: transparent;
1570                    color: #000000;
1571                    padding: 6px;
1572                    border-radius: 5px;
1573                    font-family: Arial;
1574                    font-size: 16px;
1575                    border: 1px solid #B0BEC5;
1576                    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
1577                }
1578                QMessageBox QPushButton:hover {
1579                    background: #2196F3;
1580                    border: 1px solid #2196F3;
1581                    color: #FFFFFF;
1582                }
1583            """
1584
1585    def apply_theme(self):
1586        self.setStyleSheet("""
1587            QMainWindow {
1588                background: %s;
1589            }
1590        """ % ("#263238" if self.is_dark_mode else "#F5F7FA"))
1591        self.sidebar_content.setStyleSheet(self.get_sidebar_style())
1592        self.input_card.setStyleSheet(self.get_card_style())
1593        self.username_input.setStyleSheet(self.get_input_style())
1594        self.password_input.setStyleSheet(self.get_input_style())
1595        self.reel_url_input.setStyleSheet(self.get_input_style())
1596        self.message_input.setStyleSheet(self.get_input_style())
1597        self.save_button.setStyleSheet(self.get_button_style())
1598        self.start_button.setStyleSheet(self.get_button_style())
1599        self.stop_button.setStyleSheet(self.get_button_style())
1600        self.clear_logs_button.setStyleSheet(self.get_button_style())
1601        self.logs.setStyleSheet(self.get_input_style())
1602        self.user_guide.setStyleSheet(self.get_input_style())
1603        self.summary_label.setStyleSheet(self.get_label_style())
1604        self.progress_bar.setStyleSheet(self.get_progress_style())
1605        self.dm_limit_label.setStyleSheet(self.get_label_style())
1606        self.dm_limit_input.setStyleSheet(self.get_input_style())
1607        self.password_settings_input.setStyleSheet(self.get_input_style())
1608        self.save_settings_button.setStyleSheet(self.get_button_style())
1609        self.statusBar.setStyleSheet(self.get_label_style())
1610        self.logo_label.setStyleSheet(self.get_logo_style())
1611        if self.reply_window:
1612            self.reply_window.is_dark_mode = self.is_dark_mode
1613            self.reply_window.apply_theme()
1614        if self.follow_unfollow_window:
1615            self.follow_unfollow_window.is_dark_mode = self.is_dark_mode
1616            self.follow_unfollow_window.apply_theme()
1617        if self.analytics_window:
1618            self.analytics_window.is_dark_mode = self.is_dark_mode
1619            self.analytics_window.apply_theme()
1620
1621    def toggle_mode(self):
1622        self.is_dark_mode = not self.is_dark_mode
1623        self.apply_theme()
1624        self.log(f"Switched to {'Dark' if self.is_dark_mode else 'Normal'} mode", "success")
1625        self.show_notification(f"Switched to {'Dark' if self.is_dark_mode else 'Normal'} mode", "success")
1626
1627    def switch_page(self, index):
1628        try:
1629            if index == 2:  # Analytics
1630                if not self.analytics_window:
1631                    self.analytics_window = AnalyticsWindow(self.is_dark_mode)
1632                self.analytics_window.show()
1633            elif index == 3:  # Reply DMs
1634                if not self.reply_window:
1635                    username = self.username_input.text().strip()
1636                    password = self.password_input.text().strip()
1637                    if not all([username, password]):
1638                        self.log("Please enter username and password in the main page or save in settings!", "error")
1639                        self.show_notification("Please enter username and password!", "error")
1640                        return
1641                    self.reply_window = ReplyDMWindow(self.is_dark_mode, self.cookie_file, username, password)
1642                self.reply_window.show()
1643            elif index == 4:  # Follow/Unfollow
1644                if not self.follow_unfollow_window:
1645                    username = self.username_input.text().strip()
1646                    password = self.password_input.text().strip()
1647                    if not all([username, password]):
1648                        self.log("Please enter username and password in the main page or save in settings!", "error")
1649                        self.show_notification("Please enter username and password!", "error")
1650                        return
1651                    self.follow_unfollow_window = FollowUnfollowWindow(self.is_dark_mode, self.cookie_file, username, password)
1652                self.follow_unfollow_window.show()
1653            elif index in [5, 6, 7, 8, 9]:  # New features
1654                self.log("Feature coming soon!", "info")
1655                self.show_notification("Feature coming soon!", "info")
1656            else:
1657                for i, page in enumerate(self.pages):
1658                    page.hide() if i != index else page.show()
1659                self.current_page = index
1660        except Exception as e:
1661            self.log(f"Error opening page: {str(e)}", "error")
1662            self.show_notification(f"Error opening page: {str(e)}", "error")
1663
1664    def log(self, message, message_type="info"):
1665        color = {"info": "#000000" if not self.is_dark_mode else "#FFFFFF",
1666                 "success": "#4CAF50",
1667                 "error": "#F44336"}.get(message_type, "#000000" if not self.is_dark_mode else "#FFFFFF")
1668        self.logs.append(f'<span style="color: {color}; font-family: Arial;">[{time.strftime("%H:%M:%S")}] {message}</span>')
1669        self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())
1670
1671    def update_summary(self, successful, failed, total):
1672        self.summary_label.setText(f"DMs Sent: {successful} | Failed: {failed} | Remaining: {total - successful - failed}")
1673
1674    def show_notification(self, message, message_type):
1675        msg = QMessageBox()
1676        msg.setWindowTitle("Notification")
1677        msg.setText(message)
1678        msg.setStyleSheet(self.get_notification_style())
1679        msg.exec_()
1680
1681    def update_stats(self, successful_dms, failed_dms):
1682        self.successful_dms = successful_dms
1683        self.failed_dms = failed_dms
1684
1685    def start_bot(self):
1686        if self.bot_thread and self.bot_thread.isRunning():
1687            self.log("Bot is already running!", "error")
1688            self.show_notification("Bot is already running!", "error")
1689            return
1690
1691        username = self.username_input.text()
1692        password = self.password_input.text()
1693        reel_url = self.reel_url_input.text()
1694        messages = self.message_input.toPlainText().strip().split("\n")
1695        messages = [msg.strip() for msg in messages if msg.strip()]
1696        try:
1697            dm_limit = int(self.dm_limit_input.text())
1698            if dm_limit < 10 or dm_limit > 200:
1699                raise ValueError
1700        except ValueError:
1701            self.log("Please enter a valid DM limit (10-200)!", "error")
1702            self.show_notification("Invalid DM limit!", "error")
1703            return
1704
1705        if not all([username, password, reel_url, messages]):
1706            self.log("Please fill all fields!", "error")
1707            self.show_notification("Please fill all fields!", "error")
1708            return
1709
1710        self.bot_thread = BotThread(username, password, reel_url, messages, self.cookie_file, dm_limit)
1711        self.bot_thread.log_signal.connect(self.log)
1712        self.bot_thread.progress_signal.connect(self.progress_bar.setValue)
1713        self.bot_thread.status_signal.connect(self.statusBar.showMessage)
1714        self.bot_thread.summary_signal.connect(self.update_summary)
1715        self.bot_thread.notification_signal.connect(self.show_notification)
1716        self.bot_thread.stats_signal.connect(self.update_stats)
1717        self.bot_thread.finished_signal.connect(self.bot_finished)
1718        self.bot_thread.start()
1719
1720        self.start_button.setEnabled(False)
1721        self.stop_button.setEnabled(True)
1722        self.statusBar.showMessage("Starting bot...")
1723        self.log("Starting bot...", "info")
1724        self.summary_label.setText("DMs Sent: 0 | Failed: 0 | Remaining: 0")
1725
1726    def stop_bot(self):
1727        if self.bot_thread:
1728            self.bot_thread.running = False
1729            self.bot_thread.wait()
1730        self.start_button.setEnabled(True)
1731        self.stop_button.setEnabled(False)
1732        self.statusBar.showMessage("Bot stopped")
1733        self.log("Bot stopped by user", "error")
1734        self.show_notification("Bot stopped by user", "error")
1735
1736    def bot_finished(self):
1737        self.start_button.setEnabled(True)
1738        self.stop_button.setEnabled(False)
1739        self.statusBar.showMessage("Ready")
1740        self.bot_thread = None
1741
1742    def clear_logs(self):
1743        self.logs.clear()
1744        self.log("Logs cleared", "success")
1745        self.show_notification("Logs cleared", "success")
1746
1747    def save_settings(self):
1748        settings = {
1749            "username": self.username_input.text(),
1750            "password": self.password_input.text() or self.password_settings_input.text(),
1751            "reel_url": self.reel_url_input.text(),
1752            "messages": self.message_input.toPlainText(),
1753            "dm_limit": self.dm_limit_input.text()
1754        }
1755        try:
1756            with open(self.settings_file, 'wb') as file:
1757                pickle.dump(settings, file)
1758            self.log("Settings saved successfully", "success")
1759            self.show_notification("Settings saved successfully", "success")
1760        except Exception as e:
1761            self.log(f"Error saving settings: {str(e)}", "error")
1762            self.show_notification(f"Error saving settings: {str(e)}", "error")
1763
1764    def load_settings(self):
1765        if os.path.exists(self.settings_file):
1766            try:
1767                with open(self.settings_file, 'rb') as file:
1768                    settings = pickle.load(file)
1769                self.username_input.setText(settings.get("username", ""))
1770                self.password_input.setText(settings.get("password", ""))
1771                self.reel_url_input.setText(settings.get("reel_url", ""))
1772                self.message_input.setText(settings.get("messages", ""))
1773                self.dm_limit_input.setText(str(settings.get("dm_limit", 50)))
1774                self.password_settings_input.setText(settings.get("password", ""))
1775                self.log("Settings loaded successfully", "success")
1776            except Exception as e:
1777                self.log(f"Error loading settings: {str(e)}", "error")
1778
1779if __name__ == "__main__":
1780    check_control_file()  # Check control.txt before starting the app
1781    app = QApplication(sys.argv)
1782    app.setStyle("Fusion")
1783    app.setFont(QFont("Arial", 16))
1784    window = InstagramBotApp()
1785    window.show()
1786    sys.exit(app.exec_())