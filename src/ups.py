#!/usr/bin/python3

import datetime
import json
import logging
import os
import socketserver
import sys
import time
from threading import Thread

from powerpi import Powerpi

log_level = logging.INFO
log_format = "%(asctime)s | %(levelname)-8s | %(message)s"
log_date_format = "%Y-%m-%dT%H:%M:%S"
try:
    log_file = f"/var/log/ups/{datetime.datetime.utcnow().strftime('%Y_%m_%dT%H_%M_%S')}_ups.log"
    logging.basicConfig(
        format=log_format,
        datefmt=log_date_format,
        level=log_level,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.info(f"Log file: {log_file}")
    del log_file
except PermissionError:
    logging.basicConfig(level=log_level, format=log_format, datefmt=log_date_format)
    logging.warning("Not running as sudo, log file will not be created")
del log_level
del log_format
del log_date_format

GPIO4_AVAILABLE = True
try:
    import RPi.GPIO as GPIO
except:
    GPIO4_AVAILABLE = False
    logging.error("Error importing GPIO library, UPS will work without interrupt")

ENABLE_MESSAGES = False
ENABLE_TCP = True
serverAddressPort = ("127.0.0.1", 40001)
disconnect_flag = False
latest_status = ""
ppi = Powerpi()

startTime = datetime.datetime.utcnow()
endTime = startTime


class UPSHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        cmd = self.rfile.readline().strip().decode("utf-8")
        logging.debug(cmd)
        if cmd == "status":
            self.wfile.write((latest_status + "\n").encode("utf-8"))


def multiline_log(msg, level):
    for line in msg.split("\n"):
        logging.log(level, line)


def send_message(msg, level):
    global ENABLE_MESSAGES
    multiline_log(msg, level)
    os.system(f'echo "{msg}" | wall -n') if ENABLE_MESSAGES else None


def print_ups_active_time():
    global startTime, endTime
    dt = endTime - startTime
    sec = dt.total_seconds()
    msg = f"Time UPS was active:\nTotal seconds: {sec:.2f}\nTotal minutes: {sec / 60:.2f}\nTotal hours: {sec / 3600:.2f}\nTotal days: {sec / 86400:.2f}"
    send_message(msg, logging.INFO)


def read_status(clear_fault=False):
    global disconnect_flag, latest_status
    global startTime, endTime
    err, status = ppi.read_status(clear_fault)

    if err:
        time.sleep(1)
        return

    if status["PowerInputStatus"] == "Not Connected" and not disconnect_flag:
        disconnect_flag = True
        message = f"Power Disconnected, system will shutdown in {status['TimeRemaining']:d} minutes!"
        send_message(message, logging.WARNING)
        startTime = datetime.datetime.utcnow()

    if status["PowerInputStatus"] == "Connected" and disconnect_flag:
        disconnect_flag = False
        message = f"Power Restored, battery at {status['BatteryPercentage']:d} percent"
        send_message(message, logging.INFO)
        endTime = datetime.datetime.utcnow()
        print_ups_active_time()

    latest_status = json.dumps(status, indent=4, sort_keys=True)

    logging.debug(status)

    if status["BatteryVoltage"] < ppi.VBAT_LOW:
        ppi.bat_disconnect()
        send_message("UPS depleted, shutting down", logging.CRITICAL)
        endTime = datetime.datetime.utcnow()
        print_ups_active_time()
        time.sleep(1)
        os.system("sudo shutdown now")


def interrupt_handler(channel):
    read_status(True)


def read_status_loop() -> None:
    while True:
        read_status()


def main():
    if ppi.initialize():
        sys.exit(1)

    if GPIO4_AVAILABLE:
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(
                4, GPIO.FALLING, callback=interrupt_handler, bouncetime=200
            )
        except Exception as ex:
            logging.error(
                "Error attaching interrupt to GPIO4, UPS will work without interrupt."
            )

    try:
        if ENABLE_TCP:
            logging.info(f"Starting TCP server: {serverAddressPort[0]}:{serverAddressPort[1]}")
            update_thread = Thread(target=read_status_loop, name="Read status loop")
            update_thread.setDaemon(True)
            update_thread.start()
            with socketserver.TCPServer(serverAddressPort, UPSHandler) as server:
                server.serve_forever()
        else:
            read_status_loop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
