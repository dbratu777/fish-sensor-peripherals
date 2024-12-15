import os
import glob
import time
import Adafruit_ADS1x15
import RPi.GPIO
from RPLCD.i2c import CharLCD

### ----------------------- CONSTANTS
_ORP_SENSOR_PIN          = 1
_ORP_REFERENCE_VOLTAGE   = 4900  # mV
_ORP_ZERO_VOLTAGE        = 2385  # ~= 0 mV ORP
_ORP_SLOPE               = -0.708
_ORP_RELAY_PIN           = 24
_PH_SENSOR_PIN          = 0
_PH_REFERENCE_VOLTAGE    = 4900  # mV
_PH_SLOPE                = 200
_PH_NEUTRAL_VOLTAGE      = 3235  # ~= pH 7 (in mV)
_TEMP_RELAY_PIN          = 23

_ADC = Adafruit_ADS1x15.ADS1115(busnum=1)
_GAIN = 1

### ----------------------- SENSOR AND GPIO SETUP

os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

_TEMP_DIR = glob.glob('/sys/bus/w1/devices/' + '28*')  # Look for DS18B20 devices
if not _TEMP_DIR:
    print("\nERROR: DS18B20 SENSOR NOT FOUND.\n")
    exit(1)
_TEMP_FILE = _TEMP_DIR[0] + '/w1_slave'

RPi.GPIO.setmode(RPi.GPIO.BCM)
RPi.GPIO.setup(_ORP_RELAY_PIN, RPi.GPIO.OUT)
RPi.GPIO.setup(_TEMP_RELAY_PIN, RPi.GPIO.OUT)
RPi.GPIO.output(_ORP_RELAY_PIN, RPi.GPIO.LOW)
RPi.GPIO.output(_TEMP_RELAY_PIN, RPi.GPIO.LOW)

### ----------------------- DISSOLVED OXYGEN FUNCTIONS
def read_orp():
    voltage = _ADC.read_adc(_ORP_SENSOR_PIN, gain=_GAIN) / 32767.0 * _ORP_REFERENCE_VOLTAGE
    if not voltage:
        print(f'\nWARNING: UNABLE TO READ VOLTAGE FROM ORP SENSOR ON PIN {_ORP_SENSOR_PIN}\n')
        return 0.0
    return (voltage - _ORP_ZERO_VOLTAGE) / _ORP_SLOPE

def orp_relay(orp_value):
    if orp_value < 50:
        RPi.GPIO.output(_ORP_RELAY_PIN, RPi.GPIO.HIGH)
        print(f'\tORP RELAY: ON')
    elif orp_value > 80:
        RPi.GPIO.output(_ORP_RELAY_PIN, RPi.GPIO.LOW)
        print(f'\tORP RELAY: OFF')

### ----------------------- PH FUNCTIONS
def read_ph(temperature):
    del temperature # deg C
    # pH calculation formula based on Nernstian response
    voltage = _ADC.read_adc(_PH_SENSOR_PIN, gain=_GAIN) / 32767.0 * _PH_REFERENCE_VOLTAGE
    if not voltage:
        print(f'\nWARNING: UNABLE TO READ VOLTAGE FROM PH SENSOR ON PIN {_PH_SENSOR_PIN}\n')
        return 0.0
    return (_PH_NEUTRAL_VOLTAGE - voltage) / _PH_SLOPE

def ph_calibration(voltage, temperature):
    del voltage
    del temperature # deg C
    # calibrating with known pH buffers
    pass

### ----------------------- TEMPERATURE FUNCTIONS
def read_temp():
    def raw_temp():
        with open(_TEMP_FILE, 'r') as f:
            lines = f.readlines()
        return lines

    lines = raw_temp()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = raw_temp()
    
    temp_string = lines[1].split('t=')[1]
    temp_f = (float(temp_string) / 1000.0) * (9.0 / 5.0) + 32.0
    return temp_f

def temp_relay(temp_f, threshold): 
    if temp_f < (threshold):
        # if RPi.GPIO.input(_TEMP_RELAY_PIN) == RPi.GPIO.LOW:
        RPi.GPIO.output(_TEMP_RELAY_PIN, RPi.GPIO.HIGH)
        print(f'\tTEMP RELAY: ON')
    elif temp_f > (threshold + 2):
        # if RPi.GPIO.input(_TEMP_RELAY_PIN) == RPi.GPIO.HIGH:
        RPi.GPIO.output(_TEMP_RELAY_PIN, RPi.GPIO.LOW)
        print(f'\tTEMP RELAY: OFF')


try:
    temperature_threshold = float(input("Temperature Threshold (in °F): "))
    
    while True:
        temp_f = read_temp()
        orp = read_orp()
        pH = read_ph((temp_f - 32) * (5.0 / 9.0))
        

        print(f'TEMP READING: {temp_f:.2f} °F')
        print(f'ORP READING: {orp:.2f} mV')
        print(f'PH READING: {pH:.2f} pH')

        temp_relay(temp_f, temperature_threshold)
        orp_relay(orp)

        lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2, dotsize=8)
        lcd.clear()

        lcd.cursor_pos = (0, 0)

        lcd.write_string(f'TEMP: {temp_f:.2f}')
        lcd.write_string(f'ORP: {orp:.2f}')
        lcd.write_string(f'PH: {pH:.2f}')

        time.sleep(1)

except KeyboardInterrupt:
    print("\nINFO: KEYBOARD INTERRUPT DETECTED - SHUTTING DOWN\n")
    
finally:
    RPi.GPIO.cleanup()