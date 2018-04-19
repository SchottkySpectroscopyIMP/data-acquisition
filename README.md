# Data Acquisition for Schottky Resonator at CSRe
A remote control program to record Schottky signal and archive the data files in the server.

On the hardware side, it consists of a spectrum analyzer [`FSVR-7`](https://www.rohde-schwarz.com/us/product/fsvr-productstartpage_63493-11047.html), a data recorder [`IQR-100`](https://www.rohde-schwarz.com/us/product/iqr-productstartpage_63493-11213.html), and a home-made trigger system (see a separate [repo](https://github.com/SchottkySpectroscopyIMP/ArduinoTriggerSystem) for details) largely based on [`Arduino Yún`](https://store.arduino.cc/usa/arduino-yun).
Simply stating, the work flow goes like first sampling the RF signal into a digital IQ stream by the `FSVR-7` upon the trigger events provided by the `Arduino Yún`, then recording the IQ digits as data files by the `IQR-100` and transferring them back to the server.

## Prerequisites
  1. daq.py
      - `Python 3`
      - `sys`, `re`, `time`
      - `socket`, `logging`, `subprocess`, `json`
      - `PyQt5.QtCore`, `PyQt5.QtWidgets`, `PyQt5.QtGui`
  2. multithread.py
      - `traceback`, `sys`
      - `PyQt5.QtCore`
 
## Usage
  1. Put `daq.py` and `multithread.py` in the same folder
  2. Launch the program `python3 daq.py`
  3. Wait the calibration of `FSVR` (all the button is disabled), then set acquisition parameters (hit the `set button` to lock the parameters):
      - `center frequency` (default: 242.9 MHz)
      - `span` (default: 500 kHz)
      - `reference level` (default: -50 dBm)
      - `duration` (default: 10 s)
  4. choose the acquisition mode:
      - trigger mode:
        - `auto` (default, using the trigger signal to start collecting)
        - `manual` (2 seconds after pushing `start button` to start collecting)
      - collecting file mode:
        - `continuously collecting` (default, successively acquiring data before pushing `pause button`)
        - `fixed file collecting` (stop after acquiring the set number of the files)
  5. Hit the `start button` to start the acquisition
  6. Exit mode:
      - `Ctrl + w` (pop a message box to confirm the exit operation, hit `yes` to quit)
        - during the acquistion processing: waiting the current file to be finished, then quit the program
        - at stop status: quit after hitting `yes`
      - `X button` (immediately quit the system without any prompt)
  7. Logging file (all important event will be recorded in daq.log)

## License
This repository is licensed under the **GNU GPLv3**.
