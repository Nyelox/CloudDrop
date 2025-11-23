from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QMainWindow
from PyQt5.uic import loadUi


class SendFile(QMainWindow):
   def __init__(self):
       super().__init__()
       loadUi("sendfile.ui", self)