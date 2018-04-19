#!/usr/bin/env python3
# −*− coding:utf-8 −*−

'''
This script provides a generic solution to multithreading a process used in a PyQt application,
to prevent the graphical interface from being unresponsive to end user's interactions.
It is heavily borrowed from a nice example by Martin Fitzpatrick at
https://martinfitzpatrick.name/article/multithreading-pyqt-applications-with-qthreadpool/
To use, import it into an empty script and sub-class QMainWindow for the GUI frontend design.
'''

import traceback, sys
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class Worker(QRunnable):
    '''
    the worker thread which runs the time-consuming and/or heavy-lifting functions
    '''

    def __init__(self, func, *args, **kwargs):
        '''
        func:       callback function to be run on this thread
        args:       arguments to be passed to the callback function
        kwargs:     keyword arguments to be passed to the callback function
        '''
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        kwargs['stdscr'] = self.signals.progress

    @pyqtSlot()
    def run(self):
        '''
        initialize the runner function with passed args and kwargs
        '''
        try:
            result = self.func(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class WorkerSignals(QObject):
    '''
    Define the signals available from a running worker thread.
    Supported signals are:
        finished:   `none`, empty
        result:     `object`, anything returned from processing
        error:      `tuple`, (exctype, value, traceback.format_exc() )
    '''

    finished = pyqtSignal()
    result   = pyqtSignal("PyQt_PyObject")
    progress = pyqtSignal(int)
    error    = pyqtSignal(tuple)
