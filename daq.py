#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import sys, re
import socket, time, logging, subprocess, json
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from multithread import Worker, WorkerSignals

logging.basicConfig(
    level       = logging.INFO,
    format      = '%(asctime)s %(name)-5s %(message)s',
    datefmt     = '%Y-%m-%d %H:%M:%S',
    filename    = __file__[:-2] + 'log',
    filemode    = 'a')


class instrument():
    def __init__(self, IP, port, logger):
        self.IP = IP
        self.port = port
        self.logger = logger
        self.connect()
        self.reset()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.IP, self.port))

    def disconnect(self):
        self.sock.close()

    def write(self, cmd):
        cmd += '\n'
        self.sock.send(cmd.encode("utf-8"))

    def read(self):
        data = self.sock.recv(4096)
        return data.decode("utf-8").strip()

    def reset(self):
        self.write("*RST; *WAI; *CLS")


class FSVR(instrument):
    def __init__(self, IP):
        super(FSVR, self).__init__(IP, 5025, logging.getLogger("FSVR"))
        self.write("*CAL?")
        # sleep 12 s for initial
        
    def acquire(self, CF, SRat, RLev, stdscr):
        '''
        CF:   center frequency [Hz]
        SRat: sampling rate [Hz]
        RLev: reference level [dBm]
        '''
        print("FSVR: start acquire")
        self.write("TRAC:IQ ON")
        self.write("FREQuency:CENTer {:g}MHz".format(CF/1e6))
        self.write("TRACe:IQ:SRATe {:g}MHz".format(SRat/1e6))
        self.write("DISP:TRAC:Y:RLEV {:g}dBm".format(RLev))
        self.write("INP:ATT:AUTO OFF")
        self.write("INP:ATT 0dB")
        self.write("OUTPut:DIQ ON")
        self.write("OUTPut:UPOR:STAT ON")
        self.logger.info("initialization is ready")
        
        # start data streaming
        self.write("INITiate")
        self.logger.info("data is streaming...")
        print("FSVR: streaming")


class IQR(instrument):
    def __init__(self, IP, FileSize, SRat):
        super(IQR, self).__init__(IP, 5025, logging.getLogger("IQR"))
        self.signals = WorkerSignals()
        '''
        SRat: sampling rate [Hz]
        FileSize: number of samples to be recorded in one file
        '''
        self.duraTime = FileSize / SRat # s
        self.write("INSTrument:SELect:MODE RECorder")
        # set the recodering data name 'data'
        self.write("INPut:RECorder:WAVeform:SELect 'e:/" + "data" +"'")
        self.write("INPut:RECorder:LIMits:CONDition FILesize")
        self.write("INPut:RECorder:LIMits:FILesize {:d}".format(FileSize))
        self.write("TRIGger:RECorder:SYNC SALone")
        self.write("TRIGger:RECorder:SOURce MANual")
        time.sleep(1)

        self.write("TRIGger:RECorder:ARM ONNO")
        self.logger.info("initialization is ready")

    def record(self, fileNumber, fileName):

        def loop_arm(): # sponge time to wait for IQR arming
            self.write("STATus:RECorder?")
            data = self.read()
            if data == '1':
                self.signals.progress.emit(-1)
                self.dt1 = time.time() - self.t0
                self.logger.info("recording file {:d} '{:s}'".format(fileNumber, fileName))
                self.logger.debug('estimated time of finish {:.2f} s'.format(self.duraTime))
                self.t = 0
                loop_record()
                return
            else:
                QTimer.singleShot(100, loop_arm)

        def loop_record(): # recording
            self.write("STATus:RECorder?")
            data = self.read()
            if data == '0':
                self.t = 1
                self.signals.progress.emit(100)
                self.logger.info("file {:d} '{:s}' is recorded".format(fileNumber, fileName))
                self.dt2 = time.time() - self.dt1 - self.t0
                self.signals.result.emit((self.dt1, self.dt2))
                self.signals.finished.emit()
                return
            else:
                percentVal = int(self.t*100/self.duraTime) if int(self.t*100/self.duraTime) < 99 else 99
                self.signals.progress.emit(percentVal)
                self.t += .1
                QTimer.singleShot(100, loop_record)
                
        print("IQR record start")

        self.write("TRIGger:RECorder:STARt")
        self.logger.debug('preparing, please wait...')

        self.t0 = time.time()
        loop_arm()


    def export(self, fileNumber, fileName):

        def loop_wait(): # sponge time to wait for IQR wiping out its memory
            self.write("SYSTem:ARCHive:RUNNing?")
            data = self.read()
            if data != '0':
                loop_export()
                return
            else:
                QTimer.singleShot(100, loop_wait)

        def loop_export(): # exporting
            self.write("SYSTem:ARCHive:PROGress?")
            data = self.read()
            percentVal = data.strip('"')[:-1] if data.strip('"') != '' else ' '
            if data == '"100 %"':
                self.signals.progress.emit(100)
                self.dt = time.time() - self.t0
                self.logger.info("file {:d} '{:s}' is exported".format(fileNumber, fileName))
                self.signals.result.emit(self.dt)
                self.signals.finished.emit()
                return
            else:
                self.signals.progress.emit(int(percentVal))
                QTimer.singleShot(100, loop_export)

        print("IQR export start")

        self.write("SYSTem:ARCHive:SOURce:FILEname 'e:/" + "data" + "'")
        # the address of the netdisk 
        self.write("SYSTem:ARCHive:DESTination:FILEname 'x:/" + fileName + "'")
        self.write("SYSTem:ARCHive:FORMat RAW")
        self.write("SYSTem:ARCHive:STARt")
        self.signals.progress.emit(-1)
        self.logger.debug("exporting file {:d} '{:s}', please wait...".format(fileNumber, fileName))

        self.t0 = time.time()
        loop_wait()


class DAQ_MainWindow(QMainWindow):
    '''
    The DAQ GUI Window
    '''
    def __init__(self):
        super().__init__()

        self.title = "Schottky Spectroscopy Data Acquisition Interface"
        self.left = 20
        self.top = 30
        self.width = 600
        self.height = 900

        # the default parameters setting
        self.cenFreq = 242.9    # MHz
        self.span = 500         # kHz
        self.refLev = -50       # dBm
        self.duration = 10      # s
        self.fileNumber = 1
        self.exit = False       # parameter for exit
    
        # the default color setting
        self.bgcolor = "#FAFAFA"
        self.fgcolor = "#23373B"
        self.green = "#1B813E"
        self.orange = "#E98B2A"
        self.red = "#AB3B3A"

        # set the style of the elements (QProgressBar, QLineEdit)
        # style for state of devices
        self.unset_style = """
        QProgressBar{{
            border-radius: 5px; 
            border: 1px groove silver;
            color:  {0:s};
            text-align: center
            }}
        QProgressBar::chunk{{
            border-radius: 5px; 
            background-color: #80{1:s};
            }}
        """.format(self.fgcolor, self.red[1:])
        self.wait_style = """
        QProgressBar{{
            border-radius: 5px; 
            border: 1px groove silver;
            color:  {0:s};
            text-align: center
            }}
        QProgressBar::chunk{{
            border-radius: 5px; 
            background-color: #80{1:s};
            }}
        """.format(self.fgcolor, self.orange[1:])
        self.ready_style = """
        QProgressBar{{
            border-radius: 5px; 
            border: 1px groove silver;
            color:  {0:s};
            text-align: center
            }}
        QProgressBar::chunk{{
            border-radius: 5px; 
            background-color: #80{1:s};
            }}
        """.format(self.fgcolor, self.green[1:])
        self.disable_style = """
        QProgressBar{{
            border-radius: 5px; 
            border: 1px groove silver;
            color:  {0:s};
            text-align: center
            }}
        QProgressBar::chunk{{
            border-radius: 5px; 
            background-color: transparent;
            }}
        """.format(self.fgcolor)
        # style for file recording and exporting
        self.default_style = """
        QProgressBar{{
            border: 1px groove silver;
            color:  {0:s};
            text-align: center
            }}
        QProgressBar::chunk{{
            background-color: white;
            }}
        """.format(self.fgcolor)
        self.process_style = """
        QProgressBar{{
            border: 1px groove silver;
            color:  {0:s};
            text-align: center
            }}
        QProgressBar::chunk{{
            background-color: #80{1:s};
            }}
        """.format(self.fgcolor, self.orange[1:])
        self.completed_style = """
        QProgressBar{{
            border: 1px groove silver;
            color:  {0:s};
            text-align: center
            }}
        QProgressBar::chunk{{
            background-color: #80{1:s};
            }}
        """.format(self.fgcolor, self.green[1:])
        # style for the parameter input bar
        self.stop_style = """
        QLineEdit {{
            color:  {:s};
            }}
        """.format(self.fgcolor)
        self.run_style = """
        QLineEdit {{
            color:  {:s};
            background-color:lightgray
            }}
        """.format(self.fgcolor)
        self.setup_style = """
        QLineEdit {{
            color:  {:s};
            background-color: lightgray
            }}
        """.format(self.fgcolor)

        # set the font of label
        self.fontStat = QFont("RobotoCondensed", 12)
        self.fontLab = QFont("RobotoCondensed", 14)
        self.fontProc = QFont("Inconsolata-dz", 12)
        self.fontPara = QFont("Inconsolata-dz", 24)

        # set the Icon
        self.iconStart = QIcon("./icons/play.png")
        self.iconPause = QIcon("./icons/pause.png")
        self.iconParaLock = QIcon("./icons/lock.png")
        self.iconManu = QIcon("./icons/userManual.png")

        # set folder address 
        #self.folder = "/home/schospec/Data"
        self.folder = "/home/data/"

        self.initUI()

        logging.info("application starts\n")

    def QLineEdit_StopStyle(self, lineEdit):
        lineEdit.setStyleSheet(self.stop_style)
        lineEdit.setReadOnly(False)

    def QLineEdit_RunStyle(self, lineEdit):
        lineEdit.setStyleSheet(self.run_style)
        lineEdit.setReadOnly(True)

    def QLineEdit_SetupStyle(self, lineEdit):
        lineEdit.setStyleSheet(self.setup_style)
        lineEdit.setReadOnly(True)

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.setStyleSheet("QLabel{{color: {0:s} }} QCheckBox{{background-color: {1:s}; color: {0:s}}} QTextEdit{{color: {0:s}}} QMainWindow{{ background-color: {1:s} }} QCentralWidget{{ background-color: {1:s} }} QGroupBox{{ background-color: {1:s} }}".format(self.fgcolor, self.bgcolor))
        
        self.threadPool = QThreadPool()

        self.setDisplayPanel()
        self.buildConnection()

        self.statusBar().setFont(self.fontStat)
        self.statusBar().showMessage("set the parameters before run")

    def setDisplayPanel(self):
        # set the FSVR status display
        self.FSVRLab = QLabel("FSVR")
        self.FSVRLab.setFont(self.fontLab)
        self.FSVRStatus = QProgressBar()
        self.FSVRStatus.setFont(self.fontStat)
        self.FSVRStatus.setStyleSheet(self.unset_style)
        self.FSVRStatus.setFormat("unset")
        self.FSVRStatus.setValue(100)

        # set the IQR status display
        self.IQRLab = QLabel("IQR")
        self.IQRLab.setFont(self.fontLab)
        self.IQRStatus = QProgressBar()
        self.IQRStatus.setFont(self.fontStat)
        self.IQRStatus.setStyleSheet(self.unset_style)
        self.IQRStatus.setFormat("unset")
        self.IQRStatus.setValue(100)

        # set the Arduino status display
        self.ArduinoLab = QLabel("Arduino")
        self.ArduinoLab.setFont(self.fontLab)
        self.ArduinoTriggerStatus = QProgressBar()
        self.ArduinoTriggerStatus.setFont(self.fontStat)
        self.ArduinoTriggerStatus.setStyleSheet(self.ready_style)
        self.ArduinoTriggerStatus.setFormat("triggered")
        self.ArduinoTriggerStatus.setValue(100)

        # set the IQR record status display
        self.IQRrecordStatus = QProgressBar()
        self.IQRrecordStatus.setFont(self.fontStat)
        self.IQRrecordStatus.setStyleSheet(self.default_style)
        self.IQRrecordStatus.setFormat("unrecorded")
        self.IQRrecordStatus.setValue(100)

        # set the IQR export status display
        self.IQRexportStatus = QProgressBar()
        self.IQRexportStatus.setFont(self.fontStat)
        self.IQRexportStatus.setStyleSheet(self.default_style)
        self.IQRexportStatus.setFormat("unexported")
        self.IQRexportStatus.setValue(100)

        # set the current file information display
        self.currentFileLab = QLabel("collecting file # -")
        self.currentFileLab.setFont(self.fontLab)
        self.currentFileNameLab = QLabel(time.strftime("%Y%m%d", time.localtime()) + "_------")
        self.currentFileNameLab.setFont(self.fontPara)

        # set the file acquisition mode
        self.fileModecheck = QCheckBox("maximum files", self)
        self.fileModecheck.setFont(self.fontLab)
        self.fileModecheck.setStyleSheet("QCheckBox::indicator:unchecked{border: 1px groove silver; background-color: white}")
        self.fileMaxNumInput = QLineEdit("10", self)
        self.fileMaxNumInput.setFont(self.fontProc)
        self.QLineEdit_SetupStyle(self.fileMaxNumInput)

        # set the run mode button
        self.runModeButton =  QPushButton()
        self.runModeButton.setIcon(self.iconManu)
        self.runModeButton.setFixedSize(40, 40)
        self.runModeButton.setIconSize(QSize(25, 25))

        # set the working status button
        self.statusButton = QPushButton()
        self.statusButton.setIcon(self.iconStart)
        self.statusButton.setFixedSize(40, 40)
        self.statusButton.setIconSize(QSize(25, 25))

        # set the workStatus panel
        workStatusGrid = QGridLayout()
        workStatusGrid.setSpacing(5)
        workStatusGrid.addWidget(self.FSVRLab, 0, 0, 1, 2, Qt.AlignHCenter)
        workStatusGrid.addWidget(self.FSVRStatus, 1, 0, 1, 2)
        workStatusGrid.addWidget(self.IQRLab, 0, 2, 1, 2, Qt.AlignHCenter)
        workStatusGrid.addWidget(self.IQRStatus, 1, 2, 1, 2)
        workStatusGrid.addWidget(self.ArduinoLab, 0, 4, 1, 2, Qt.AlignHCenter)
        workStatusGrid.addWidget(self.ArduinoTriggerStatus, 1, 4, 1, 2)
        workStatusGrid.addWidget(self.IQRrecordStatus, 2, 0, 1, 3)
        workStatusGrid.addWidget(self.IQRexportStatus, 2, 3, 1, 3)
        workStatusGrid.addWidget(self.fileModecheck, 3, 0, 1, 4)
        workStatusGrid.addWidget(self.fileMaxNumInput, 3, 4, 1, 2)
        workStatusGrid.addWidget(self.runModeButton, 3, 6, 1, 1, Qt.AlignRight)
        workStatusGrid.addWidget(self.statusButton, 3, 7, 1, 1, Qt.AlignRight)
        workStatusGrid.addWidget(self.currentFileLab, 0, 6, 1, 2, Qt.AlignHCenter)
        workStatusGrid.addWidget(self.currentFileNameLab, 1, 6, 2, 2, Qt.AlignVCenter)
        
        self.workStatusPanel = QGroupBox()
        self.workStatusPanel.setStyleSheet("QGroupBox{border: 1px groove silver; margin: 1px; padding-top: 0}")
        self.workStatusPanel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.workStatusPanel.setLayout(workStatusGrid)

        # set the file log display
        self.fileLogText = QTextEdit()
        self.fileLogText.setFont(self.fontProc)
        self.fileLogText.setReadOnly(True)
        self.fileLogText.setStyleSheet("QTextEdit{{border: 2px groove silver; color: {:s}; background-color: lightgray}}".format(self.fgcolor))

        # set the parameter input LineEdit
        self.cenFreqLab = QLabel("center frequency [MHz]")
        self.cenFreqLab.setFont(self.fontLab)
        self.cenFreqInput = QLineEdit(str(self.cenFreq))
        self.cenFreqInput.setFont(self.fontProc)
        self.QLineEdit_RunStyle(self.cenFreqInput)

        self.spanLab = QLabel("span [kHz]")
        self.spanLab.setFont(self.fontLab)
        self.spanInput = QLineEdit(str(self.span))
        self.spanInput.setFont(self.fontProc)
        self.QLineEdit_RunStyle(self.spanInput)

        self.durationLab = QLabel("duration [s]")
        self.durationLab.setFont(self.fontLab)
        self.durationInput = QLineEdit(str(self.duration))
        self.durationInput.setFont(self.fontProc)
        self.QLineEdit_RunStyle(self.durationInput)

        self.refLevLab = QLabel("reference level [dBm]")
        self.refLevLab.setFont(self.fontLab)
        self.refLevInput = QLineEdit(str(self.refLev))
        self.refLevInput.setFont(self.fontProc)
        self.QLineEdit_RunStyle(self.refLevInput)

        # set the setPara button
        self.setButton = QPushButton()
        self.setButton.setIcon(self.iconParaLock)
        self.setButton.setFixedSize(40, 40)
        self.setButton.setIconSize(QSize(25,25))

        # set the parameter panel layout
        self.paraLayout = QGridLayout()
        self.paraLayout.setSpacing(5)
        self.paraLayout.addWidget(self.cenFreqLab, 0, 0, 1, 1)
        self.paraLayout.addWidget(self.cenFreqInput, 0, 1, 1, 1)
        self.paraLayout.addWidget(self.spanLab, 0, 2, 1, 1)
        self.paraLayout.addWidget(self.spanInput, 0, 3, 1, 1)
        self.paraLayout.addWidget(self.refLevLab, 1, 0, 1, 1)
        self.paraLayout.addWidget(self.refLevInput, 1, 1, 1, 1)
        self.paraLayout.addWidget(self.durationLab, 1, 2, 1, 1)
        self.paraLayout.addWidget(self.durationInput, 1, 3, 1, 1)
        self.paraLayout.addWidget(self.setButton, 2, 3, 1, 1, Qt.AlignRight)

        self.paraPanel = QGroupBox()
        self.paraPanel.setStyleSheet("QGroupBox{border: 1px groove silver; margin: 1px; padding: 0}")
        self.paraPanel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.paraPanel.setLayout(self.paraLayout)

        windowLayout = QVBoxLayout()
        windowLayout.setSpacing(5)
        windowLayout.addWidget(self.workStatusPanel)
        windowLayout.addWidget(self.paraPanel)
        windowLayout.addWidget(self.fileLogText)
        wid = QWidget()
        self.setCentralWidget(wid)
        wid.setLayout(windowLayout)

    def buildConnection(self):
        # build connection with fileMode - checkbox
        def button_fileMode():
            if self.fileModecheck.isChecked():
                self.QLineEdit_StopStyle(self.fileMaxNumInput)
            else:
                self.QLineEdit_SetupStyle(self.fileMaxNumInput)
        self.fileModecheck.stateChanged.connect(button_fileMode)

        # build connection with userAuto - pushbutton
        def button_userAuto():
            if self.runModeButton.isChecked():
                # Manual mode
                self.IQR_init_worker.signals.finished.disconnect(IQR_init_ready_auto)
                self.IQR_init_worker.signals.finished.connect(IQR_init_ready_manu)
                self.ArduinoTriggerStatus.setFormat("disabled")
                self.ArduinoTriggerStatus.setStyleSheet(self.disable_style)
            else:
                # Auto mode
                try:
                    self.IQR_init_worker.signals.finished.disconnect(IQR_init_ready_manu)
                except:
                    pass
                self.IQR_init_worker.signals.finished.connect(IQR_init_ready_auto)
                self.ArduinoTriggerStatus.setFormat("triggered")
                self.ArduinoTriggerStatus.setStyleSheet(self.ready_style)
        self.runModeButton.toggled.connect(button_userAuto)
        self.runModeButton.setEnabled(False)
        self.runModeButton.setCheckable(True)
        

        # build connection with paraChange - pushbutton
        def button_paraLock():
            if self.setButton.isChecked():
                self.cenFreq = float(self.cenFreqInput.text())
                self.span = float(self.spanInput.text())
                self.refLev = float(self.refLevInput.text())
                self.duration = float(self.durationInput.text())
                self.QLineEdit_SetupStyle(self.cenFreqInput)
                self.QLineEdit_SetupStyle(self.spanInput)
                self.QLineEdit_SetupStyle(self.refLevInput)
                self.QLineEdit_SetupStyle(self.durationInput)
                self.metadata = {
                    "center frequency": self.cenFreq*1e6, # Hz
                    "span": self.span*1e3, # Hz
                    "reference level": self.refLev, # dBm
                    "duration": self.duration, # s
                }
                self.metadata["sampling rate"] = self.metadata["span"] * 1.25
                self.metadata["number of samples"] = (int((self.metadata["sampling rate"] * self.metadata["duration"]) / 2621440) + 1) * 2621440
                self.metadata["format"] = "int16"
                self.metadata["endian"] = "little"
                self.metadata["resolution"] = 16 # bits
                self.FSVR_acquire_worker = Worker(self.fsvr.acquire, self.metadata["center frequency"], self.metadata["sampling rate"], self.metadata["reference level"])
                self.FSVR_acquire_worker.signals.finished.connect(FSVR_acquire_ready)
                self.IQR_init_worker = Worker(IQR_init_work, self.metadata["number of samples"], self.metadata["sampling rate"])
                self.IQR_init_worker.signals.finished.connect(IQR_init_ready_auto)
                self.ArduinoTriggerStatus.setFormat("triggered")
                self.ArduinoTriggerStatus.setStyleSheet(self.ready_style)
                self.statusBar().showMessage("all parameters are set")
                self.statusButton.setEnabled(True)
                self.runModeButton.setEnabled(True)
                self.runModeButton.setChecked(False)
            else:
                self.QLineEdit_StopStyle(self.cenFreqInput)
                self.QLineEdit_StopStyle(self.spanInput)
                self.QLineEdit_StopStyle(self.refLevInput)
                self.QLineEdit_StopStyle(self.durationInput)
                self.statusBar().showMessage("please set new parameter values")
                self.statusButton.setEnabled(False)
                self.runModeButton.setEnabled(False)
        self.setButton.setEnabled(False)
        self.setButton.setCheckable(True)
        self.setButton.toggled.connect(button_paraLock)

        # build connection with play - pushbutton
        def button_play():
            # status - run
            self.fileModecheck.setEnabled(False)
            self.runModeButton.setEnabled(False)
            self.setButton.setEnabled(False)
            self.QLineEdit_RunStyle(self.cenFreqInput)
            self.QLineEdit_RunStyle(self.spanInput)
            self.QLineEdit_RunStyle(self.refLevInput)
            self.QLineEdit_RunStyle(self.durationInput)
            self.QLineEdit_RunStyle(self.fileMaxNumInput)
            self.statusButton.pressed.disconnect(button_play)
            self.statusButton.pressed.connect(button_pause)
            self.statusButton.setCheckable(True)
            self.statusButton.setChecked(True)
            self.statusButton.setIcon(self.iconPause)
            self.statusBar().showMessage("data acquisition running")
            self.threadPool.start(self.FSVR_acquire_worker)
            print("play")
            self.TotalDt1 = self.TotalDt2 = self.TotalDt3 = 0
            self.fileFixNumber = 1

        def button_pause():
            if self.statusButton.isCheckable():
                # status - pause - (stop by pushbutton)
                self.statusButton.setCheckable(False)
                self.statusBar().showMessage("data acquisition to be stopped on completion")
                self.statusButton.pressed.disconnect(button_pause)
                self.statusButton.pressed.connect(button_play)
            else:
                # status - pause - (stop by file number limit)
                self.statusButton.pressed.disconnect(button_pause)
                self.statusButton.pressed.connect(button_play)
                print("stop by file")
                button_play()
        self.statusButton.setEnabled(False)
        self.statusButton.pressed.connect(button_play)

        # build FSVR work
        def FSVR_init_work(stdscr):
            self.fsvr = FSVR("10.10.91.95")
        def FSVR_init_ready():
            self.FSVRStatus.setFormat("running")
            self.FSVRStatus.setStyleSheet(self.ready_style)
            self.setButton.setEnabled(True)
            self.setButton.setChecked(False)
            self.QLineEdit_StopStyle(self.cenFreqInput)
            self.QLineEdit_StopStyle(self.spanInput)
            self.QLineEdit_StopStyle(self.refLevInput)
            self.QLineEdit_StopStyle(self.durationInput)
        # start calibrating FSVR
        self.FSVR_init_worker = Worker(FSVR_init_work)
        self.threadPool.start(self.FSVR_init_worker)
        self.FSVRStatus.setFormat("calibrating")
        self.FSVRStatus.setStyleSheet(self.wait_style)
        QTimer.singleShot(12000, FSVR_init_ready)

        def FSVR_acquire_ready():
            print("FSVR: ready")
            self.threadPool.start(self.IQR_init_worker)

        # build Arduino work
        def Arduino_work(stdscr):
            # kill the process on port 5025 to prevent nc address occupied error
            popen = subprocess.Popen(['netstat', '-lpn'], shell=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            (data, err) = popen.communicate()
            pattern = "^tcp.*(?:5025).* (?P<pid>[0-9]*)/.*$"
            prog = re.compile(pattern)
            for line in data.decode().split('\n'):
                match = re.match(prog, line)
                if match != None:
                    pid = match.group('pid')
                    subprocess.Popen(['kill', '-9', pid])

            while True:
                with subprocess.Popen(["nc", "-l", "5025"], stdout=subprocess.PIPE) as netcat: # magic command: iptables -F
                    message = netcat.stdout.readline().strip().decode("utf-8")
                    if message == "triggered":
                        logging.getLogger("YUN").info("Arduino is triggered")
                        break
        def Arduino_ready():
            self.ArduinoTriggerStatus.setFormat("triggered")
            self.ArduinoTriggerStatus.setStyleSheet(self.ready_style)
            # fileName setting
            timestamp = time.localtime()
            self.fileName = time.strftime("%Y%m%d", timestamp) + "_" + time.strftime("%H%M%S", timestamp)
            self.metadata["timestamp"] = time.strftime("%Y", timestamp) + "-" +\
                                time.strftime("%m", timestamp) + "-" +\
                                time.strftime("%d", timestamp) + "T" +\
                                time.strftime("%H", timestamp) + ":" +\
                                time.strftime("%M", timestamp) + ":" +\
                                time.strftime("%S", timestamp) +\
                                time.strftime("%z", timestamp)
            self.currentFileNameLab.setText(self.fileName)
            self.currentFileLab.setText("collecting file # " + str(self.fileNumber))
            self.thread_record.started.connect(lambda: self.iqr.record(self.fileNumber, self.fileName))
            self.thread_record.finished.connect(IQR_record_ready)
            print("auto-connect")
            self.iqr.signals.progress.connect(IQR_record_process)
            self.iqr.signals.result.connect(IQR_record_result)
            self.iqr.signals.finished.connect(self.thread_record.quit)
            self.thread_record.start()
            self.thread_export.started.connect(lambda: self.iqr.export(self.fileNumber, self.fileName))
            self.thread_export.finished.connect(IQR_export_ready)

        # build IQR work
        def IQR_init_work(FileSize, SRat, stdscr):
            print("IQR: init start!")
            self.iqr = IQR("10.10.91.93", FileSize, SRat)
        def IQR_init_ready_auto():
            self.IQRStatus.setFormat("running")
            self.IQRStatus.setStyleSheet(self.ready_style)
            self.Arduino_worker = Worker(Arduino_work)
            self.Arduino_worker.signals.finished.connect(Arduino_ready)
            self.ArduinoTriggerStatus.setFormat("waiting")
            self.ArduinoTriggerStatus.setStyleSheet(self.wait_style)
            QTimer.singleShot(2000, lambda: self.threadPool.start(self.Arduino_worker))
            self.thread_record = QThread()
            self.thread_export = QThread()
        def IQR_init_ready_manu():
            self.IQRStatus.setFormat("running")
            self.IQRStatus.setStyleSheet(self.ready_style)
            # fileName setting
            timestamp = time.localtime(time.time() + 2)
            self.fileName = time.strftime("%Y%m%d", timestamp) + "_" + time.strftime("%H%M%S", timestamp)
            self.metadata["timestamp"] = time.strftime("%Y", timestamp) + "-" +\
                                time.strftime("%m", timestamp) + "-" +\
                                time.strftime("%d", timestamp) + "T" +\
                                time.strftime("%H", timestamp) + ":" +\
                                time.strftime("%M", timestamp) + ":" +\
                                time.strftime("%S", timestamp) +\
                                time.strftime("%z", timestamp)
            self.currentFileNameLab.setText(self.fileName)
            self.currentFileLab.setText("collecting file # " + str(self.fileNumber))
            logging.info("manual triggered")
            self.thread_record = QThread()
            self.thread_export = QThread()
            self.thread_record.started.connect(lambda: self.iqr.record(self.fileNumber, self.fileName))
            self.thread_record.finished.connect(IQR_record_ready)
            print("manu-connect")
            self.iqr.signals.progress.connect(IQR_record_process)
            self.iqr.signals.result.connect(IQR_record_result)
            self.iqr.signals.finished.connect(self.thread_record.quit)
            QTimer.singleShot(2000, self.thread_record.start)
            self.thread_export.started.connect(lambda: self.iqr.export(self.fileNumber, self.fileName))
            self.thread_export.finished.connect(IQR_export_ready)
            return

        def IQR_record_process(percentVal):
            if percentVal == -1:
                self.IQRrecordStatus.setFormat("recording")
                self.IQRrecordStatus.setValue(0)
            elif percentVal == 100:
                self.IQRrecordStatus.setFormat("recorded")
                self.IQRrecordStatus.setStyleSheet(self.completed_style)
                self.IQRrecordStatus.setValue(100)
            else:
                self.IQRrecordStatus.setFormat("%p%")
                self.IQRrecordStatus.setStyleSheet(self.process_style)
                self.IQRrecordStatus.setValue(percentVal)
        def IQR_record_result(result):
            self.dt1, self.dt2 = result
        def IQR_record_ready():
            self.iqr.signals.progress.disconnect(IQR_record_process)
            self.iqr.signals.result.disconnect(IQR_record_result)
            self.iqr.signals.finished.disconnect(self.thread_record.quit)
            print("record-disconnect")
            self.iqr.signals.progress.connect(IQR_export_process)
            self.iqr.signals.result.connect(IQR_export_result)
            self.iqr.signals.finished.connect(self.thread_export.quit)
            print("export-connect")
            QTimer.singleShot(1000, self.thread_export.start)

        def IQR_export_process(percentVal):
            if percentVal == -1:
                self.IQRexportStatus.setFormat("exporting")
                self.IQRexportStatus.setValue(0)
            elif percentVal == 100:
                self.IQRexportStatus.setFormat("exported")
                self.IQRexportStatus.setStyleSheet(self.completed_style)
                self.IQRexportStatus.setValue(100)
            else:
                self.IQRexportStatus.setFormat("%p%")
                self.IQRexportStatus.setStyleSheet(self.process_style)
                self.IQRexportStatus.setValue(percentVal)
        def IQR_export_result(result):
            self.dt3 = result
        def IQR_export_ready():
            with open(self.folder + self.fileName + ".wvh", 'w') as header:
                json.dump(self.metadata, header, indent=4, sort_keys=True)
            self.fileLogText.append("file {:d}: {:s}\npreparing time: {:.2f} s\nrecording time: {:.2f} s\nexporting time: {:.2f} s\n".format(self.fileNumber, self.fileName, self.dt1, self.dt2, self.dt3))
            logging.info("preparing time: {:.2f} s\n{:25s} recording time: {:.2f} s\n{:25s} exporting time: {:.2f} s\n".format(self.dt1, ' ', self.dt2, ' ', self.dt3))
            print("export-disconnect")
            self.iqr.signals.progress.disconnect(IQR_export_process)
            self.iqr.signals.result.disconnect(IQR_export_result)
            self.iqr.signals.finished.disconnect(self.thread_export.quit)
            self.IQRrecordStatus.setFormat("unrecorded")
            self.IQRrecordStatus.setStyleSheet(self.default_style)
            self.IQRexportStatus.setFormat("unexported")
            self.IQRexportStatus.setStyleSheet(self.default_style)
            self.iqr.disconnect()
            self.IQRStatus.setFormat("unset")
            self.IQRStatus.setStyleSheet(self.unset_style)
            self.fileNumber += 1
            self.fileFixNumber += 1
            self.TotalDt1 += self.dt1
            self.TotalDt2 += self.dt2
            self.TotalDt3 += self.dt3
            if (not self.statusButton.isCheckable()) or (self.fileModecheck.isChecked() and self.fileFixNumber >= (int(self.fileMaxNumInput.text())+1)):
                self.fileLogText.append("total preparing time: {:.2f} s\ntotal recording time: {:.2f} s\ntotal exporting time: {:.2f} s\n\n".format(self.TotalDt1, self.TotalDt2, self.TotalDt3))
                logging.info("total preparing time: {:.2f} s\n{:25s} total recording time: {:.2f} s\n{:25s} total exporting time: {:.2f} s\n\n".format(self.TotalDt1, ' ', self.TotalDt2, ' ', self.TotalDt3))
                self.fileModecheck.setEnabled(True)
                self.setButton.setEnabled(True)
                self.setButton.setChecked(False)
                self.statusButton.setEnabled(False)
                self.statusButton.setIcon(self.iconStart)
                self.QLineEdit_SetupStyle(self.cenFreqInput)
                self.QLineEdit_SetupStyle(self.spanInput)
                self.QLineEdit_SetupStyle(self.refLevInput)
                self.QLineEdit_SetupStyle(self.durationInput)
                if self.fileModecheck.isChecked():
                    self.QLineEdit_StopStyle(self.fileMaxNumInput)
                    self.statusButton.setCheckable(False)
                else:
                    self.QLineEdit_SetupStyle(self.fileMaxNumInput)
                self.statusBar().showMessage("data acquisition stopped")
                if self.exit:
                    logging.info("application stops\n\n\n")
                    sys.exit()
            elif self.runModeButton.isChecked():
                self.IQR_init_worker = Worker(IQR_init_work, self.metadata["number of samples"], self.metadata["sampling rate"])
                self.IQR_init_worker.signals.finished.connect(IQR_init_ready_manu)
                QTimer.singleShot(1000, lambda: self.threadPool.start(self.IQR_init_worker))
            else:
                self.IQR_init_worker = Worker(IQR_init_work, self.metadata["number of samples"], self.metadata["sampling rate"])
                self.IQR_init_worker.signals.finished.connect(IQR_init_ready_auto)
                QTimer.singleShot(1000, lambda: self.threadPool.start(self.IQR_init_worker))

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_W:
            reply = QMessageBox.question(self, "Message", "Are you sure to quit?", QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.statusButton.isCheckable():
                    self.statusBar().showMessage("will exit on data acquisition completed")
                    self.statusButton.setCheckable(False)
                    self.exit = True
                    return
                else:
                    logging.info("application stops\n\n\n")
                    sys.exit()
            else:
                return

    def closeEvent(self, event):
        reply = QMessageBox.question(self, "Message", "Are you sure to force quit?", QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            subprocess.call("rm -f {:s}*.wsm".format(self.folder), shell=True)
            logging.info("application force stop\n\n\n")
            try:
                self.iqr.disconnect()
            except:
                pass
            event.accept()
            sys.exit()
        else:
            event.ignore()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    daq = DAQ_MainWindow()
    daq.show()
    sys.exit(app.exec())


