# Data Acquisition for Schottky Resonator at CSRe
A remote control program to record Schottky signal and archive the data files in the server.

On the hardware side, it consists of a spectrum analyzer [`FSVR-7`](https://www.rohde-schwarz.com/us/product/fsvr-productstartpage_63493-11047.html), a data recorder [`IQR-100`](https://www.rohde-schwarz.com/us/product/iqr-productstartpage_63493-11213.html), and a home-made trigger system (see a separate [repo](https://github.com/SchottkySpectroscopyIMP/ArduinoTriggerSystem) for details) largely based on [`Arduino Yún`](https://store.arduino.cc/usa/arduino-yun).
Simply stating, the work flow goes like first sampling the RF signal into a digital IQ stream by the `FSVR-7` upon the trigger events provided by the `Arduino Yún`, then recording the IQ digits as data files by the `IQR-100` and transferring them back to the server.

The code provides a command line interface to continuous data acquisition, i.e., a new file is being recorded as soon as the last one finished unless being interrupted by the user in the middle.

## Prerequisites
 - `Python 3`
 - `socket`, `time`, `curses`, `logging`, `subprocess`, `json`

## Usage
 1. Modify directly the source file `daq.py` to set acquisition parameters:
  - `center frequency`
  - `span`
  - `reference level`
  - `duration` (_length in time of each data file, note that the actual recording duration may differ than the setting, since the `IQR-100` constrains the file length in byte to be a multiple of the unit length 2,621,440_)
 2. Launch the program `python3 daq.py`
 3. Hit the combo keys `Ctrl + e` to pause the acquisition
 4. Once the progress is paused, press `b` to resume or press the `spacebar` to exit

## License
This repository is licensed under the **GNU GPLv3**.
