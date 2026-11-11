import sys


def main() -> None:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("缺少界面组件。请双击 启动.bat，或运行：")
        print("python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple")
        raise SystemExit(1)
    from app.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
