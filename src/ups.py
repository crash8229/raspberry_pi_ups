#!/usr/bin/python3

import time
import os, sys
import logging
import socket
import json
from powerpi import Powerpi

import datetime

logging.basicConfig(level=logging.INFO)
GPIO4_AVAILABLE = True

try:
    import RPi.GPIO as GPIO   
except :
    GPIO4_AVAILABLE = False
    logging.error("Error importing GPIO library, UPS will work without interrupt")

ENABLE_MESSAGES = False
ENABLE_UDP = True
UDP_PORT = 40001
serverAddressPort   = ("127.0.0.1", UDP_PORT)
UDPClientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
disconnectflag = False
ppi = Powerpi()

startTime = datetime.datetime.utcnow()
endTime = startTime

def send_message(msg):
    global ENABLE_MESSAGES
    os.system(msg) if ENABLE_MESSAGES else None

def print_time_delta():
    global startTime, endTime
    dt = endTime - startTime
    sec = dt.total_seconds()
    send_message(f'echo "Time UPS was active:\nTotal seconds: {sec:.2f}\nTotal minutes: {sec/60:.2f}\nTotal hours: {sec/3600:.2f}\nTotal days: {sec/86400:.2f}" | wall -n')

def save_ups_time():
    global startTime, endTime
    dt = endTime - startTime
    sec = dt.total_seconds()
    with open(f"/var/log/ups/{datetime.datetime.utcnow().strftime('%Y_%m_%dT%H_%M_%S')}_ups.log", "w") as f:
        f.write(f"Time UPS was active before shutdown:\nTotal seconds: {sec:.2f}\nTotal minutes: {sec/60:.2f}\nTotal hours: {sec/3600:.2f}\nTotal days: {sec/86400:.2f}")

def read_status(clear_fault=False):
        global disconnectflag, ENABLE_UDP
        global startTime, endTime
        err, status = ppi.read_status(clear_fault)
        
        if err:
            time.sleep(1)
            return

        if status["PowerInputStatus"] == "Not Connected" and disconnectflag == False :
            disconnectflag = True
            message = "echo Power Disconnected, system will shutdown in %d minutes! | wall -n " % (status['TimeRemaining'])
            send_message(message)
            startTime = datetime.datetime.utcnow()
        
        if status["PowerInputStatus"] == "Connected" and disconnectflag == True :
            disconnectflag = False
            message = "echo Power Restored, battery at %d percent | wall -n " % (status['BatteryPercentage'])
            send_message(message)
            endTime = datetime.datetime.utcnow()
            print_time_delta()
        
        if ENABLE_UDP:
            try:
                UDPClientSocket.sendto(json.dumps(status,indent=4,sort_keys=True).encode("utf-8"), serverAddressPort)
            except Exception as ex:
                logging.error(ex)
        
        logging.debug(status)
        
        if status['BatteryVoltage'] < ppi.VBAT_LOW:
                ppi.bat_disconnect()
                send_message("echo UPS depleted, shutting down | wall -n")
                endTime = datetime.datetime.utcnow()
                save_ups_time()
                time.sleep(1)
                os.system('sudo shutdown now')

def interrupt_handler(channel):
    read_status(True) 

def main():
    if ppi.initialize():
        sys.exit(1)

    if GPIO4_AVAILABLE:
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(4, GPIO.FALLING, callback=interrupt_handler, bouncetime=200)
        except Exception as ex:
            logging.error("Error attaching interrupt to GPIO4, UPS will work without interrupt.")
    
    while (True):
        read_status()

if __name__=="__main__":
    main()
                
