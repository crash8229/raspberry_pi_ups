import smbus
import logging
import time

class Powerpi:
    
    #Refer to http://www.ti.com/lit/ds/symlink/bq25895.pdf for register maps


    ####Edit this section to suit your battery and input specs##############################

    """
    BYTE_ILIM is used to set the input current limit, i.e the maximum current the
    UPS will draw from the power input. It does not affect the output current from
    the UPS. If more current is required at the output than the input is cpabale of,
    the UPS will augment that current from the battery.
    """
    #BYTE_ILIM =  0b01101000 #2A input current limit
    BYTE_ILIM =  0b01111111 #3.25A input current limit
    #BYTE_ICHG =  0b00001000 #.5A charging current limit
    BYTE_ICHG =  0b00010000 #1A charging current limit
    
    VBAT_LOW = 3.2 # Determines the battery voltage at which the UPS will shutoff. 
    
    #Charge Voltage, uncomment the line suitable for your battery type.
    #BYTE_VREG = 0b00000010 #3.84v
    #BYTE_VREG = 0b00010010 #3.9V
    #BYTE_VREG = 0b00101010 #4V
    #BYTE_VREG = 0b01000110 #4.112V
    BYTE_VREG = 0b01011110 #4.208V
    #BYTE_VREG = 0b01110110 #4.304V
    #BYTE_VREG = 0b10001110 #4.4V
    #BYTE_VREG = 0b10101010 #4.512V
    #BYTE_VREG = 0b11000010 #4.608V

    """    
    BAT_CAPACITY, CURRENT_DRAW and VBAT_MAX are used to estimated the state of charge 
    of the battery since there is not current sensor on this UPS. These values along
    with the battery voltage is used to derive the state of charge of the battery.
_    
    To make the charge percent of the battery shown more accurate, take a note of
    the battery voltage when charging is complete (red LED turns off after plugging in) 
    and edit the VBAT_MAX to that value.
    
    NB:Changing these values does not affect or change the behavior of the UPS.
    """
    BAT_CAPACITY = 3500 #Battery capacity in mAh
    CURRENT_DRAW = 370 #Current draw in mAh approximately
    VBAT_MAX = 4.17 #This should be the battery when charged to a 100%

    ##################################################################################


    PORT = 1
    ADDRESS = 0x6a      #I2C address of the ups

    REG_WATCHDOG = 0x07
    BYTE_WATCHDOG_STOP =  0b10001101 #Stop Watchdog timer
    REG_SYSMIN = 0x03
    BYTE_SYSMIN = 0b00010000
    REG_ILIM = 0x00 #ILIM register
    REG_VREG = 0x06 #Charge voltage register

    REG_ICHG = 0x04 
    REG_ICHGR = 0x12
    REG_CONV_ADC = 0x02
    REG_BATFET = 0x09
    BYTE_BATFET = 0b01001000 #delay before battery is disconnected

    REG_CONV_ADC = 0x02
    BYTE_CONV_ADC_START = 0b10011101
    BYTE_CONV_ADC_STOP = 0b00011101
    REG_BATFET_DIS = 0x09
    BYTE_BATFET_DIS = 0b01101000
    REG_STATUS = 0x0B #address of status register
    REG_VBAT = 0x0e
    REG_FAULT = 0x0c
    REG_IBAT = 0x12
    REG_VBUS = 0x11
    

    def __init__(self):
        pass        
        
    def initialize(self):
        try:
            self.bus = smbus.SMBus(self.PORT)
            self.bus.write_byte_data(self.ADDRESS, self.REG_WATCHDOG, self.BYTE_WATCHDOG_STOP)
            self.bus.write_byte_data(self.ADDRESS, self.REG_ILIM,self.BYTE_ILIM)
            self.bus.write_byte_data(self.ADDRESS, self.REG_ICHG, self.BYTE_ICHG)
            self.bus.write_byte_data(self.ADDRESS, self.REG_BATFET, self.BYTE_BATFET)
            self.bus.write_byte_data(self.ADDRESS, self.REG_SYSMIN, self.BYTE_SYSMIN)
            self.bus.write_byte_data(self.ADDRESS, self.REG_VREG, self.BYTE_VREG)
            logging.info("UPS initialized")
            return 0
        except Exception as ex:
            logging.error("Initialization failed, check connection to the UPS:"+ str(ex))
            return 1 
    
    def _int_to_bool_list(self,num):
        return [bool(num & (1<<n)) for n in range(8)]
    
    def _vbat_convert(self,vbat_byte):
        vbat_bool = self._int_to_bool_list(vbat_byte)
        vbat = 2.304
        vbat += vbat_bool[6] * 1.280
        vbat += vbat_bool[5] * 0.640
        vbat += vbat_bool[4] * 0.320
        vbat += vbat_bool[3] * 0.160
        vbat += vbat_bool[2] * 0.08
        vbat += vbat_bool[1] * 0.04
        vbat += vbat_bool[0] * 0.02   
        return vbat
    
    def _ibat_convert(self,ibat_byte):
        ibat_bool = self._int_to_bool_list(ibat_byte)
        ibat = 0
        ibat += ibat_bool[6] * 3200
        ibat += ibat_bool[5] * 1600
        ibat += ibat_bool[4] * 800
        ibat += ibat_bool[3] * 400
        ibat += ibat_bool[2] * 200
        ibat += ibat_bool[1] * 100
        ibat += ibat_bool[0] * 50
        return ibat

    def _vbus_convert(self,vbus_byte):
        vbus_bool = self._int_to_bool_list(vbus_byte)
        vbus = 2.6
        vbus += vbus_bool[6] * 6.4
        vbus += vbus_bool[5] * 3.2
        vbus += vbus_bool[4] * 1.6
        vbus += vbus_bool[3] * 0.8
        vbus += vbus_bool[2] * 0.4
        vbus += vbus_bool[1] * 0.2
        vbus += vbus_bool[0] * 0.1
        return vbus

    def _calc_bat_charge_percent(self,vbat):
        bat_charge_percent = (vbat-self.VBAT_LOW)/(self.VBAT_MAX - self.VBAT_LOW)
        if bat_charge_percent < 0:
            bat_charge_percent = 0
        elif bat_charge_percent > 1:
            bat_charge_percent = 1
        return bat_charge_percent
    
    def _calc_time_left(self,vbat):
        time_left = int(self._calc_bat_charge_percent(vbat) * 60 * self.BAT_CAPACITY / self.CURRENT_DRAW)
        if time_left < 0:
            time_left = 0
        return time_left

    def read_status(self, clear_fault=False):
        try:
            if clear_fault:
                self.bus.read_byte_data(self.ADDRESS, self.REG_FAULT)
            self.bus.write_byte_data(self.ADDRESS, self.REG_CONV_ADC, self.BYTE_CONV_ADC_START)
            time.sleep(2)
            status = self.bus.read_byte_data(self.ADDRESS, self.REG_STATUS)
            status = self._int_to_bool_list(int(status))            
            vbat = self._vbat_convert(self.bus.read_byte_data(self.ADDRESS, self.REG_VBAT))            
            ibat = self._ibat_convert(self.bus.read_byte_data(self.ADDRESS, self.REG_ICHGR))
            vbus = self._vbus_convert(self.bus.read_byte_data(self.ADDRESS, self.REG_VBUS))
            self.bus.write_byte_data(self.ADDRESS, self.REG_CONV_ADC, self.BYTE_CONV_ADC_STOP)
        except Exception as ex:
            logging.error("An exception occurred while reading values from the UPS: " + str(ex))
            time.sleep(2)
            return 1, None
        
        if status[2]:
            power_status = "Connected"
            time_left = -1
        else:
            power_status = "Not Connected"
            time_left = self._calc_time_left(vbat)

        if status[3] and status[4]:
            charge_status = "Charging done"
        elif status[4] and  not status[3]:
            charge_status = "Charging"
        elif not status[4] and status[3]:
            charge_status = "Pre-Charge"
        else:
            charge_status = "Not Charging"
        
        
        data = { 
            'PowerInputStatus': power_status,
            'InputVoltage' : round(vbus,3),
            'ChargeStatus' : charge_status,
            'BatteryVoltage' : round(vbat,3),
            "BatteryPercentage" : int(self._calc_bat_charge_percent(vbat)*100),
            'ChargeCurrent' : ibat,
            'TimeRemaining' : int(time_left)
        }

        return 0, data

    def bat_disconnect(self):
        for i in (0,3):
            try:
                self.bus.write_byte_data(self.ADDRESS, self.REG_BATFET_DIS, self.BYTE_BATFET_DIS)
                return 0
            except:
                time.sleep(1)
        return 1
