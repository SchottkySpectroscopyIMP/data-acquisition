# Data Acquisition for Schottky Resonator at CSRe
A remote control program to record Schottky signal and archive the data files in the server.

On the hardware side, it consists of a spectrum analyzer [`FSVR-7`](https://www.rohde-schwarz.com/us/product/fsvr-productstartpage_63493-11047.html), a data recorder [`IQR-100`](https://www.rohde-schwarz.com/us/product/iqr-productstartpage_63493-11213.html), and a home-made trigger system (see a separate [repo](https://github.com/SchottkySpectroscopyIMP/ArduinoTriggerSystem) for details) largely based on [`Arduino Yún`](https://store.arduino.cc/usa/arduino-yun).
Simply stating, the work flow goes like first sampling the RF signal into a digital IQ stream by the `FSVR-7` upon the trigger events provided by the `Arduino Yún`, then recording the IQ digits as data files by the `IQR-100` and transferring them back to the server.

This implementation adopts `Qt`-based Graphical User Interface (**GUI**) to provide the end user with operational convenience.

## Installation
`daq.py` and `multithread.py` should reside in the same folder.

### Prerequisites
  - `Python 3`
  - `PyQt5`
  - `sys`, `re`, `time`, `socket`, `logging`, `subprocess`, `json`, `traceback`
 
## Usage

### Preparation

  1. Connect the server to the network and create a shared disk.
  2. Change the IP in the `Arduino Yún`'s [code](https://github.com/SchottkySpectroscopyIMP/ArduinoTriggerSystem) to the IP of server and upload the code to the `Arduino Yún`.
  3. Power all the devices (`FSVR-7`, `IQR-100`, `Arduino Yún`) and connect them to the network. (The IPs of them may need to be the same with the socket IPs in code)
  4. Map the shared disk of the server from `IQR-100`, and adjust the drive letter of the actual disk in the code.

### Operation

  1. Launch the program `python3 daq.py`
  2. Wait for the calibration of `FSVR` to complete (meanwhile all the buttons are disabled), then set acquisition parameters (hit the `set button` to lock the parameters):
      - `center frequency` (default: 242.9 MHz)
      - `span` (default: 500 kHz)
      - `reference level` (default: -50 dBm)
      - `duration` (default: 10 s)
  3. choose the acquisition mode:
      - trigger mode:
        - `auto` (default, using the trigger signal to start collecting)
        - `manual` (2 seconds after pushing `start button` to start collecting)
      - collecting file mode:
        - `continuously collecting` (default, successively acquiring data before pushing `pause button`)
        - `fixed file collecting` (stop after acquiring the set number of the files)
  4. Hit the `start button` to start the acquisition
  5. Exit mode:
      - `Ctrl + w` (pop a message box to confirm the exit operation, hit `yes` to quit)
        - during the acquistion processing: waiting the current file to be finished, then quit the program
        - at stop status: quit after hitting `yes`
      - `X button` (immediately quit the system without any prompt)

_All raw data files will be transferred to the server storage folder at the end of collection, unless the size of a single file is larger than 1 GB._

_All important events with timestamps will automatically be recorded in `daq.log`_.

## License
This repository is licensed under the **GNU GPLv3**.
