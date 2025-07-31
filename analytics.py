import sys
import time
import os
import csv
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QMessageBox, QFileDialog
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon

class AnalyticsWindow(QMainWindow):
    def __init__(self, is_dark_mode):
        super().__init__()
        self.setWindowTitle("Analytics")
        self.setGeometry(200, 200, 600, 400)
        self.is_dark_mode = is_dark_mode
        self.log_files = {
            "MainBot": "E:/DOWNLOADS/InstagramBotPython/dm_log.csv",
            "ReplyDMs": "E:/DOWNLOADS/InstagramBotPython/reply_log.csv",
            "Follow": "E:/DOWNLOADS/InstagramBotPython/follow_log.csv",
            "Unfollow": "E:/DOWNLOADS/InstagramBotPython/unfollow_log.csv"
        }

        # Check if icon directory exists
        self.icon_dir = "E:/DOWNLOADS/InstagramBotPython/icons/"
        if not os.path.exists(self.icon_dir):
            self.show_notification(f"Icon directory {self.icon_dir} not found! Using default icons.", "error")

        # UI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout()

        # Header
        self.header_label = QLabel("Analytics Dashboard")
        self.header_label.setFont(QFont("Arial", 20, QFont.Bold))
        self.header_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header_label)

        # Analytics Display
        self.analytics_text = QTextEdit()
        self.analytics_text.setReadOnly(True)
        self.analytics_text.setStyleSheet(self.get_input_style())
        self.main_layout.addWidget(self.analytics_text)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Data")
        self.refresh_button.setIcon(QIcon(os.path.join(self.icon_dir, "refresh_icon.png") if os.path.exists(os.path.join(self.icon_dir, "refresh_icon.png")) else ""))
        self.refresh_button.setFixedSize(130, 35)
        self.refresh_button.setStyleSheet(self.get_button_style())
        self.refresh_button.clicked.connect(self.refresh_data)
        self.button_layout.addWidget(self.refresh_button)

        self.download_button = QPushButton("Download CSV")
        self.download_button.setIcon(QIcon(os.path.join(self.icon_dir, "download_icon.png") if os.path.exists(os.path.join(self.icon_dir, "download_icon.png")) else ""))
        self.download_button.setFixedSize(145, 35)
        self.download_button.setStyleSheet(self.get_button_style())
        self.download_button.clicked.connect(self.download_csv)
        self.button_layout.addWidget(self.download_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setIcon(QIcon(os.path.join(self.icon_dir, "clear_icon.png") if os.path.exists(os.path.join(self.icon_dir, "clear_icon.png")) else ""))
        self.clear_button.setFixedSize(120, 35)
        self.clear_button.setStyleSheet(self.get_button_style())
        self.clear_button.clicked.connect(self.clear_logs)
        self.button_layout.addWidget(self.clear_button)

        self.main_layout.addLayout(self.button_layout)
        self.central_widget.setLayout(self.main_layout)

        # Apply initial theme
        self.apply_theme()

        # Load initial data
        self.refresh_data()

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
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    background: #455A64;
                    color: #FFFFFF;
                    font-family: Arial;
                    font-size: 16px;
                }
            """
        else:
            return """
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #B0BEC5;
                    border-radius: 5px;
                    background: #FFFFFF;
                    color: #000000;
                    font-family: Arial;
                    font-size: 16px;
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
        self.analytics_text.setStyleSheet(self.get_input_style())
        self.refresh_button.setStyleSheet(self.get_button_style())
        self.download_button.setStyleSheet(self.get_button_style())
        self.clear_button.setStyleSheet(self.get_button_style())
        self.header_label.setStyleSheet(self.get_label_style())

    def log(self, message, message_type="info"):
        color = {"info": "#000000" if not self.is_dark_mode else "#FFFFFF",
                 "success": "#4CAF50",
                 "error": "#F44336"}.get(message_type, "#000000" if not self.is_dark_mode else "#FFFFFF")
        self.analytics_text.append(f'<span style="color: {color}; font-family: Arial;">[{time.strftime("%H:%M:%S")}] {message}</span>')
        self.analytics_text.verticalScrollBar().setValue(self.analytics_text.verticalScrollBar().maximum())

    def show_notification(self, message, message_type):
        msg = QMessageBox()
        msg.setWindowTitle("Notification")
        msg.setText(message)
        msg.setStyleSheet(self.get_notification_style())
        msg.exec_()

    def refresh_data(self):
        self.analytics_text.clear()
        self.log("Refreshing analytics data...", "info")
        analytics_data = {}

        for category, log_file in self.log_files.items():
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as file:
                        reader = csv.reader(file)
                        headers = next(reader, None)  # Skip header
                        if headers is None:
                            self.log(f"No data in {category} log file", "error")
                            analytics_data[category] = {"successful": 0, "failed": 0, "details": []}
                            continue
                        data = list(reader)
                        successful = len([row for row in data if row[-1] == "Success"])
                        failed = len([row for row in data if row[-1] == "Failed"])
                        analytics_data[category] = {"successful": successful, "failed": failed, "details": data}
                except Exception as e:
                    self.log(f"Error reading {category} log: {str(e)}", "error")
                    analytics_data[category] = {"successful": 0, "failed": 0, "details": []}
            else:
                self.log(f"No log file found for {category}", "error")
                analytics_data[category] = {"successful": 0, "failed": 0, "details": []}

        # Display summary
        self.analytics_text.append("<b>Analytics Summary:</b>")
        for category, data in analytics_data.items():
            self.analytics_text.append(f"<b>{category}:</b> {data['successful']} successful, {data['failed']} failed")
            if data["details"]:
                self.analytics_text.append(f"<b>{category} Details:</b>")
                for row in data["details"]:
                    self.analytics_text.append(f"Timestamp: {row[0]}, Username: {row[1]}, Action: {row[2]}, Status: {row[3]}")
        self.log("Data refreshed successfully", "success")

    def download_csv(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Analytics Data", "", "CSV Files (*.csv)")
            if file_path:
                with open(file_path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    writer.writerow(["Category", "Timestamp", "Username", "Action", "Status"])
                    for category, log_file in self.log_files.items():
                        if os.path.exists(log_file):
                            with open(log_file, 'r', encoding='utf-8') as log:
                                reader = csv.reader(log)
                                headers = next(reader, None)  # Skip header
                                if headers is None:
                                    continue
                                for row in reader:
                                    writer.writerow([category] + row)
                self.log("Analytics data downloaded successfully", "success")
                self.show_notification("Analytics data downloaded successfully", "success")
        except Exception as e:
            self.log(f"Error downloading data: {str(e)}", "error")
            self.show_notification(f"Error downloading data: {str(e)}", "error")

    def clear_logs(self):
        self.analytics_text.clear()
        self.log("Analytics logs cleared", "success")
        self.show_notification("Analytics logs cleared", "success")