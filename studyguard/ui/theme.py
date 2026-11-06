DARK_QSS = """
* {
    font-family: "Segoe UI", "Inter", Arial;
    color: #e7f6ff;
}
QMainWindow, QWidget {
    background: #080b10;
}
QLabel#Title {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 0px;
}
QLabel#Mono {
    font-family: "Cascadia Mono", Consolas, monospace;
    color: #8ee8ff;
}
QFrame#Card, QWidget#Card {
    background: rgba(18, 25, 35, 0.92);
    border: 1px solid rgba(91, 209, 255, 0.22);
    border-radius: 8px;
}
QPushButton {
    background: #112131;
    border: 1px solid #2f9dba;
    border-radius: 8px;
    color: #e9fbff;
    padding: 10px 14px;
    font-weight: 650;
}
QPushButton:hover {
    background: #153248;
    border-color: #73e6ff;
}
QPushButton:pressed {
    background: #0f1b29;
}
QPushButton#Danger {
    border-color: #ff5c7a;
    color: #ffdce4;
}
QPushButton#Primary {
    background: #073446;
    border-color: #57dcff;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider {
    background: #0d141d;
    border: 1px solid rgba(118, 216, 255, 0.25);
    border-radius: 6px;
    padding: 6px;
}
QTabWidget::pane {
    border: 1px solid rgba(91, 209, 255, 0.18);
}
QTabBar::tab {
    background: #0d141d;
    color: #b9ddeb;
    padding: 9px 14px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #112638;
    color: #ffffff;
}
QScrollArea {
    border: 0;
}
"""
