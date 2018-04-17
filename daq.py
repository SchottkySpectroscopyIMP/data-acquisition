#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import socket, time, curses, logging, subprocess, json
logging.basicConfig(
        level    = logging.INFO,
        format   = '%(asctime)s %(name)-5s %(message)s',
        datefmt  = '%Y-%m-%d %H:%M:%S',
        filename = './' + __file__[:-2] + 'log',
        filemode = 'a')


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
        super(FSVR, self).__init__(IP, 5025, logging.getLogger('FSVR'))

    def iniSet(self, stdscr, y, CF, SRat, RLev):
        '''
        CF: center frequency in unit of Hz
        SRat: sampling rate in unit of Hz
        RLev: reference level in unit of dBm
        '''
        stdscr.addstr(y, 0, "FSVR('{:s}', {:d}) is connected".format(self.IP, self.port))
        stdscr.refresh()
        self.write("*CAL?")
        stdscr.addstr(y+1, 0, 'FSVR is being calibrated...')
        stdscr.refresh()
        time.sleep(12)
        self.write("TRAC:IQ ON")
        self.write("FREQuency:CENTer {:g}MHz".format(CF/1e6))
        self.write("TRACe:IQ:SRATe {:g}MHz".format(SRat/1e6))
        self.write("DISP:TRAC:Y:RLEV {:g}dBm".format(RLev))
        self.write("INP:ATT:AUTO OFF")
        self.write("INP:ATT 0dB")
        self.write("OUTPut:DIQ ON")
        self.write("OUTPut:UPOR:STAT ON")
        stdscr.addstr(y+1, 0, 'FSVR is all set' + ' ' * 12)
        stdscr.refresh()
        self.logger.info('initialization is ready')

    def acquire(self, stdscr, y):
        self.write("INITiate")
        stdscr.addstr(y, 0, 'FSVR: Data is streaming...')
        stdscr.refresh()
        self.logger.info('data is streaming...')
        return y+1


class IQR(instrument):
    def __init__(self, IP):
        super(IQR, self).__init__(IP, 5025, logging.getLogger('IQR'))

    def iniSet(self, stdscr, y, SRat, FileSize):
        '''
        SRat: sampling rate in unit of Hz
        FileSize: number of samples to be recorded in one file
        '''
        self.duraTime = FileSize / SRat # s
        stdscr.addstr(y, 0, "IQR('{:s}', {:d}) is connected".format(self.IP, self.port))
        stdscr.refresh()
        self.write("INSTrument:SELect:MODE RECorder")
        self.write("INPut:RECorder:LIMits:CONDition FILesize")
        self.write("INPut:RECorder:LIMits:FILesize {:d}".format(FileSize))
        self.write("TRIGger:RECorder:SYNC SALone")
        self.write("TRIGger:RECorder:SOURce MANual")
        stdscr.addstr(y+1, 0, 'IQR is all set')
        stdscr.refresh()
        self.logger.info('initialization is ready')

    def record(self, stdscr, y, fileName, fileNumber):
        self.write("INPut:RECorder:WAVeform:SELect 'e:/" + fileName + "'")
        self.write("TRIGger:RECorder:ARM ONNO")
        time.sleep(2)
        self.write("TRIGger:RECorder:STARt")
        self.logger.debug('preparing, please wait...')

        t0 = time.time()
        while True: # sponge time to wait for IQR arming
            self.write("STATus:RECorder?")
            data = self.read()
            if data == '1':
                break
            time.sleep(.1)
        dt1 = time.time() - t0
        stdscr.addstr(y, 0, "IQR: Recording file {:d} '{:s}'".format(fileNumber, fileName))
        stdscr.refresh()
        self.logger.info("recording file {:d} '{:s}'".format(fileNumber, fileName))
        self.logger.debug('estimated time of finish {:.2f} s'.format(self.duraTime))

        t = 0
        while True: # recording
            self.write("STATus:RECorder?")
            data = self.read()
            if data == "0":
                break
            stdscr.addstr(y+1, 0, "IQR: Progress {:3.0f} %".format(t*100/self.duraTime))
            stdscr.refresh()
            t += .1
            time.sleep(.1)
        stdscr.addstr(y+1, 0, "IQR: Progress 100 %")
        stdscr.refresh()
        self.logger.info("file {:d} '{:s}' is recorded".format(fileNumber, fileName))
        dt2 = time.time() - dt1 - t0
        return dt1, dt2, y+2

    def export(self, stdscr, y, fileName, fileNumber):
        time.sleep(1)
        self.write("SYSTem:ARCHive:SOURce:FILEname 'e:/" + fileName + "'")
        self.write("SYSTem:ARCHive:DESTination:FILEname 'z:/" + fileName + "'")
        self.write("SYSTem:ARCHive:FORMat RAW")
        self.write("SYSTem:ARCHive:STARt")
        stdscr.addstr(y, 0, "IQR: Exporting file {:d} '{:s}'".format(fileNumber, fileName))
        stdscr.refresh()
        self.logger.debug("exporting file {:d} '{:s}', please wait...".format(fileNumber, fileName))

        t0 = time.time()
        while True: # sponge time to wait for IQR wiping out its memory
            self.write("SYSTem:ARCHive:RUNNing?")
            data = self.read()
            if data != '0':
                break
            time.sleep(.1)

        while True: # exporting
            self.write("SYSTem:ARCHive:PROGress?")
            data = self.read()
            stdscr.addstr(y+1, 0, "IQR: Progress {:s}".format(data.strip('"')))
            stdscr.refresh()
            if data == '"100 %"':
                break
            time.sleep(.1)
        dt = time.time() - t0
        self.logger.info("file {:d} '{:s}' is exported".format(fileNumber, fileName))

        self.write("MMEMory:CDIRectory 'e:'")
        self.write("MMEMory:DELete '" + fileName + ".ws1'; *WAI")
        time.sleep(.1)
        self.write("MMEMory:DELete '" + fileName + ".wsm'; *WAI")
        time.sleep(.1)
        self.write("MMEMory:CDIRectory 'f:'")
        self.write("MMEMory:DELete '" + fileName + ".ws2'; *WAI")
        time.sleep(.1)
        return dt, y+2


def main(stdscr):
    curses.echo() # echo every input character on the screen
    stdscr.nodelay(True) # non-blocking getch()
    stdscr.addstr(0, 0, "Hit 'Ctrl-e' to quit:", curses.A_STANDOUT)
    stdscr.refresh()

    metadata = {
            "center frequency": 245e6, # Hz
            "span": 5e6, # Hz
            "reference level": -45., # dBm
            "duration": 2, # s
            }
    metadata["sampling rate"] = metadata["span"] * 1.25
    metadata["number of samples"] = (int((metadata["sampling rate"] * metadata["duration"]) / 2621440) + 1) * 2621440

    folder = "/home/schospec/Data/"
    fsvr = FSVR("10.10.91.95")
    iqr = IQR("10.10.91.93")
    fsvr.iniSet(stdscr, 2, metadata["center frequency"], metadata["sampling rate"], metadata["reference level"])
    iqr.iniSet(stdscr, 4, metadata["sampling rate"], metadata["number of samples"])
    logging.info('application starts\n')
    TotalDt1 = TotalDt2 = TotalDt3 = 0
    run, fileNumber = True, 1

    while run:
        y = 7 if fileNumber % 2 == 1 else 16
        stdscr.addstr(y, 0, ' ' * 60 + ('\n' + ' ' * 60) * 8) # erase the second to last print
        y = fsvr.acquire(stdscr, y)

        timestamp = time.localtime()
        fileName = time.strftime('%Y%m%d', timestamp) + '_' + time.strftime('%H%M%S', timestamp)
        metadata["timestamp"] = time.strftime("%Y", timestamp) + '-' +\
                time.strftime("%m", timestamp) + '-' +\
                time.strftime("%d", timestamp) + 'T' +\
                time.strftime("%H", timestamp) + ':' +\
                time.strftime("%M", timestamp) + ':' +\
                time.strftime("%S", timestamp) +\
                time.strftime("%z", timestamp)
        dt1, dt2, y = iqr.record(stdscr, y, fileName, fileNumber)
        dt3, y = iqr.export(stdscr, y, fileName, fileNumber)
        stdscr.addstr(y, 0, "preparing time: {:.2f} s\nrecording time: {:.2f} s\nexporting time: {:.2f} s".format(dt1, dt2, dt3))
        stdscr.refresh()
        logging.info("preparing time: {:.2f} s\n{:25s} recording time: {:.2f} s\n{:25s} exporting time: {:.2f} s\n".format(dt1, ' ', dt2, ' ', dt3))

        metadata["format"] = "int16"
        metadata["endian"] = "little"
        metadata["resolution"] = 16 # bits
        time.sleep(.1)
        with open(folder + fileName + ".wvh", 'w') as header:
            json.dump(metadata, header, indent=4, sort_keys=True)
        fileNumber += 1
        TotalDt1 += dt1
        TotalDt2 += dt2
        TotalDt3 += dt3

        if stdscr.getch(0, 22) == 5: # Ctrl-e was pressed during the process
            stdscr.addstr(25, 0,'total preparing time: {:.2f} s\ntotal recording time: {:.2f} s\ntotal exporting time: {:.2f} s'.format(TotalDt1, TotalDt2, TotalDt3))
            stdscr.addstr(28, 0, "Exit or not? Press 'space' to the terminal, 'b' to continue.", curses.A_STANDOUT)
            stdscr.refresh()

            while True:
                key = stdscr.getch(0, 25)
                if key == ord(' '):
                    fsvr.disconnect()
                    iqr.disconnect()
                    run = False
                    break
                elif key == ord('b'):
                    stdscr.addstr(25, 0, ' ' * 60 + ('\n' + ' ' * 60) * 3)
                    stdscr.refresh()
                    break

    subprocess.call("rm -f {:s}*.wsm".format(folder), shell=True)
    logging.info("application stops\n{:25s} total preparing time: {:.2f} s\n{:25s} total recording time: {:.2f} s\n{:25s} total exporting time: {:.2f} s\n\n".format(' ', TotalDt1, ' ', TotalDt2, ' ', TotalDt3))



if __name__ == "__main__":
    curses.wrapper(main)
