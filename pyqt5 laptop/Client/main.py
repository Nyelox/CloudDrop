import sys
from PyQt5.QtWidgets import QApplication
from Login import Login

def main():
    app = QApplication(sys.argv)


    login_window = Login()
    login_window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
