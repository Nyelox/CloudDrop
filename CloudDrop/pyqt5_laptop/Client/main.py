import sys
import os
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)
sys.path.append(os.path.join(root_dir, "Server"))

from PyQt5.QtWidgets import QApplication
from Login import Login


def main():
    app = QApplication(sys.argv)

    login_window = Login()
    login_window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
