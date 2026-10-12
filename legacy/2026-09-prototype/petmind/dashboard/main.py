"""
PetMind PyQt6 대시보드

실행:
    python petmind/dashboard/main.py
"""
import sys
import requests
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QGroupBox,
    QSpinBox, QStatusBar, QSplitter, QHeaderView,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

API_BASE = "http://localhost:8000"

BEHAVIOR_EMOJI = {
    "happy":   "😊",
    "anxious": "😟",
    "playing": "🎾",
    "resting": "😴",
    "alert":   "⚠️",
}
EMOTION_EMOJI = {
    "happy":   "😄",
    "sad":     "😢",
    "angry":   "😠",
    "neutral": "😐",
}
BEHAVIOR_COLOR = {
    "happy":   "#4CAF50",
    "anxious": "#FF9800",
    "playing": "#2196F3",
    "resting": "#9E9E9E",
    "alert":   "#F44336",
}


class FetchWorker(QThread):
    """백그라운드에서 API 호출 후 결과를 시그널로 전달."""
    analysis_ready = pyqtSignal(list)
    feeding_ready  = pyqtSignal(list)
    connected      = pyqtSignal(bool)

    def run(self):
        try:
            r = requests.get(f"{API_BASE}/analysis/", params={"limit": 20}, timeout=2)
            self.analysis_ready.emit(r.json())
            self.connected.emit(True)
        except Exception:
            self.connected.emit(False)

        try:
            r = requests.get(f"{API_BASE}/feeding/", params={"limit": 20}, timeout=2)
            self.feeding_ready.emit(r.json())
        except Exception:
            pass


class FeedWorker(QThread):
    """급식 명령을 백그라운드에서 전송."""
    done = pyqtSignal(bool, str)  # (성공여부, 메시지)

    def __init__(self, amount: int):
        super().__init__()
        self.amount = amount

    def run(self):
        try:
            r = requests.post(
                f"{API_BASE}/feeding/",
                json={"amount_g": self.amount, "triggered_by": "manual"},
                timeout=3,
            )
            if r.status_code == 200:
                self.done.emit(True, f"급식 완료: {self.amount}g ({datetime.now().strftime('%H:%M:%S')})")
            else:
                self.done.emit(False, f"급식 실패: 서버 오류 {r.status_code}")
        except Exception as e:
            self.done.emit(False, f"급식 실패: {e}")


class StatusCard(QWidget):
    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(QFont("Arial", 10))
        self.title_lbl.setStyleSheet("color: #888;")

        self.value_lbl = QLabel("—")
        self.value_lbl.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.conf_lbl = QLabel("")
        self.conf_lbl.setFont(QFont("Arial", 10))
        self.conf_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conf_lbl.setStyleSheet("color: #aaa;")

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.conf_lbl)
        self.setStyleSheet("background:#1e1e2e; border-radius:10px;")

    def update(self, value: str, conf: float = 0.0, color: str = "#fff"):
        self.value_lbl.setText(value)
        self.value_lbl.setStyleSheet(f"color: {color};")
        self.conf_lbl.setText(f"{conf*100:.0f}%" if conf else "")


class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PetMind 대시보드")
        self.setMinimumSize(900, 650)
        self.setStyleSheet("background:#13131f; color:#eee;")

        self._fetch_worker = None
        self._feed_worker  = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── 헤더 ──────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("🐾 PetMind")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.conn_lbl = QLabel("● 연결 중...")
        self.conn_lbl.setStyleSheet("color: #888; font-size: 12px;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.conn_lbl)
        root.addLayout(header)

        # ── 상태 카드 ─────────────────────────────────────
        cards_layout = QHBoxLayout()
        self.behavior_card   = StatusCard("행동 인식")
        self.emotion_card    = StatusCard("감정 분석")
        self.feed_count_card = StatusCard("오늘 급식")
        cards_layout.addWidget(self.behavior_card)
        cards_layout.addWidget(self.emotion_card)
        cards_layout.addWidget(self.feed_count_card)
        root.addLayout(cards_layout)

        # ── 급식 제어 ─────────────────────────────────────
        feed_box = QGroupBox("급식 제어")
        feed_box.setStyleSheet(
            "QGroupBox { color:#ccc; border:1px solid #333; border-radius:8px; margin-top:6px; padding:8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )
        feed_layout = QHBoxLayout(feed_box)
        feed_layout.addWidget(QLabel("급식량 (g):"))

        self.amount_spin = QSpinBox()
        self.amount_spin.setRange(10, 200)
        self.amount_spin.setValue(50)
        self.amount_spin.setStyleSheet(
            "background:#2a2a3e; color:#eee; border:1px solid #444; padding:4px; border-radius:4px;"
        )
        feed_layout.addWidget(self.amount_spin)

        self.feed_btn = QPushButton("🍽️  급식 실행")
        self._feed_btn_normal = "background:#4CAF50; color:white; font-size:14px; padding:8px 20px; border-radius:6px;"
        self._feed_btn_ok     = "background:#81C784; color:white; font-size:14px; padding:8px 20px; border-radius:6px;"
        self.feed_btn.setStyleSheet(self._feed_btn_normal)
        self.feed_btn.clicked.connect(self.do_feed)
        feed_layout.addWidget(self.feed_btn)
        feed_layout.addStretch()
        root.addWidget(feed_box)

        # ── 기록 테이블 ───────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        analysis_box = QGroupBox("분석 기록 (최근 20건)")
        analysis_box.setStyleSheet(
            "QGroupBox { color:#ccc; border:1px solid #333; border-radius:8px; margin-top:6px; padding:8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )
        ab_layout = QVBoxLayout(analysis_box)
        self.analysis_table = self._make_table(["시간", "행동", "감정"])
        ab_layout.addWidget(self.analysis_table)
        splitter.addWidget(analysis_box)

        feeding_box = QGroupBox("급식 기록 (최근 20건)")
        feeding_box.setStyleSheet(
            "QGroupBox { color:#ccc; border:1px solid #333; border-radius:8px; margin-top:6px; padding:8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )
        fb_layout = QVBoxLayout(feeding_box)
        self.feeding_table = self._make_table(["시간", "급식량", "구분"])
        fb_layout.addWidget(self.feeding_table)
        splitter.addWidget(feeding_box)

        root.addWidget(splitter)

        # ── 상태바 ────────────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("PetMind 대시보드 시작됨")
        self.status_bar.setStyleSheet("color: #888;")

        # ── 타이머 (5초마다 갱신, 이전 요청 완료 후에만 시작) ──
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        self.refresh()

    def _make_table(self, headers: list) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setStyleSheet(
            "QTableWidget { background:#1e1e2e; color:#eee; border:none; gridline-color:#333; }"
            "QTableWidget::item:alternate { background:#252535; }"
            "QHeaderView::section { background:#2a2a3e; color:#ccc; padding:4px; border:none; }"
        )
        return t

    def refresh(self):
        if self._fetch_worker and self._fetch_worker.isRunning():
            return  # 이전 요청이 아직 진행 중이면 건너뜀

        self._fetch_worker = FetchWorker()
        self._fetch_worker.analysis_ready.connect(self._on_analysis)
        self._fetch_worker.feeding_ready.connect(self._on_feeding)
        self._fetch_worker.connected.connect(self._on_connected)
        self._fetch_worker.start()

    def _on_connected(self, ok: bool):
        if ok:
            self.conn_lbl.setText("● 연결됨")
            self.conn_lbl.setStyleSheet("color: #4CAF50; font-size: 12px;")
        else:
            self.conn_lbl.setText("● 연결 끊김")
            self.conn_lbl.setStyleSheet("color: #F44336; font-size: 12px;")

    def _on_analysis(self, data: list):
        if data:
            latest = data[0]
            b = latest["behavior"]
            e = latest["emotion"]
            self.behavior_card.update(
                f"{BEHAVIOR_EMOJI.get(b, '')} {b}",
                latest["behavior_conf"],
                BEHAVIOR_COLOR.get(b, "#fff"),
            )
            self.emotion_card.update(
                f"{EMOTION_EMOJI.get(e, '')} {e}",
                latest["emotion_conf"],
                "#64B5F6",
            )

        self.analysis_table.setRowCount(0)
        for row in data:
            r_idx = self.analysis_table.rowCount()
            self.analysis_table.insertRow(r_idx)
            ts = row["timestamp"][:19].replace("T", " ")
            b  = row["behavior"]
            e  = row["emotion"]
            self.analysis_table.setItem(r_idx, 0, QTableWidgetItem(ts))
            b_item = QTableWidgetItem(f"{BEHAVIOR_EMOJI.get(b, '')} {b}")
            b_item.setForeground(QColor(BEHAVIOR_COLOR.get(b, "#fff")))
            self.analysis_table.setItem(r_idx, 1, b_item)
            self.analysis_table.setItem(r_idx, 2, QTableWidgetItem(f"{EMOTION_EMOJI.get(e, '')} {e}"))

    def _on_feeding(self, data: list):
        today = datetime.utcnow().date().isoformat()
        today_count = sum(1 for d in data if d["timestamp"][:10] == today)
        self.feed_count_card.update(f"{today_count}회", color="#FFB74D")

        self.feeding_table.setRowCount(0)
        for row in data:
            r_idx = self.feeding_table.rowCount()
            self.feeding_table.insertRow(r_idx)
            ts = row["timestamp"][:19].replace("T", " ")
            self.feeding_table.setItem(r_idx, 0, QTableWidgetItem(ts))
            self.feeding_table.setItem(r_idx, 1, QTableWidgetItem(f"{row['amount_g']}g"))
            self.feeding_table.setItem(r_idx, 2, QTableWidgetItem(row["triggered_by"]))

    def do_feed(self):
        if self._feed_worker and self._feed_worker.isRunning():
            return

        self.feed_btn.setEnabled(False)
        self._feed_worker = FeedWorker(self.amount_spin.value())
        self._feed_worker.done.connect(self._on_feed_done)
        self._feed_worker.start()

    def _on_feed_done(self, ok: bool, msg: str):
        self.status_bar.showMessage(msg)
        if ok:
            self.feed_btn.setStyleSheet(self._feed_btn_ok)
            QTimer.singleShot(1000, lambda: self.feed_btn.setStyleSheet(self._feed_btn_normal))
            self.refresh()
        self.feed_btn.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = Dashboard()
    win.show()
    sys.exit(app.exec())
