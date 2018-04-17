# Data Acquisition for Schottky Resonator at CSRe
A remote control program to record Schottky signal and archive the data files in the server.

On the hardware side, it consists of a spectrum analyzer [`FSVR-7`](https://www.rohde-schwarz.com/us/product/fsvr-productstartpage_63493-11047.html), a data recorder [`IQR-100`](https://www.rohde-schwarz.com/us/product/iqr-productstartpage_63493-11213.html), and a home-made trigger system (see a separate [repo](https://github.com/SchottkySpectroscopyIMP/ArduinoTriggerSystem) for details) largely based on [`Arduino Yún`](https://store.arduino.cc/usa/arduino-yun).
Simply stating, the work flow goes like first sampling the RF signal into a digital IQ stream by the `FSVR-7` upon the trigger events provided by the `Arduino Yún`, then recording the IQ digits as data files by the `IQR-100` and transferring them back to the server.

## License
This repository is licensed under the **GNU GPLv3**.
