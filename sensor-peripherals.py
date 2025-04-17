
import datetime
import glob
import os
import time
import Adafruit_ADS1x15
import RPi.GPIO

from RPLCD.i2c import CharLCD
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

# ----------------------- CONSTANTS
_ORP_SENSOR_PIN = 1
_ORP_REFERENCE_VOLTAGE = 4500  # mV
_ORP_ZERO_VOLTAGE = 2385  # ~= 0 mV ORP
_ORP_SLOPE = -0.708
_ORP_RELAY_PIN = 24
_PH_SENSOR_PIN = 0
_PH_REFERENCE_VOLTAGE = 4900  # mV
_PH_SLOPE = 200
_PH_NEUTRAL_VOLTAGE = 3235  # ~= pH 7 (in mV)
_TEMP_RELAY_PIN = 23

_ADC = Adafruit_ADS1x15.ADS1115(busnum=1)
_GAIN = 1

_ORP_THRESHOLD = 15  # (mv)
_PH_THRESHOLD = 0.5  # (pH)
_TEMP_THRESHOLD = 1  # (F)

_ALERT_STATES = {
    "Temperature": False,
    "Oxygen": False,
    "pH": False
}
_UNSET_STATES = {
    "Temperature": False,
    "Oxygen": False,
    "pH": False
}

# ----------------------- SENSOR AND GPIO SETUP

# os.system('modprobe w1-gpio')
# os.system('modprobe w1-therm')

# Look for DS18B20 devices
_TEMP_DIR = glob.glob('/sys/bus/w1/devices/' + '28*')
if not _TEMP_DIR:
    print("\nERROR: DS18B20 SENSOR NOT FOUND.\n")
    exit(1)
_TEMP_FILE = _TEMP_DIR[0] + '/w1_slave'

RPi.GPIO.setmode(RPi.GPIO.BCM)
RPi.GPIO.setup(_ORP_RELAY_PIN, RPi.GPIO.OUT)
RPi.GPIO.setup(_TEMP_RELAY_PIN, RPi.GPIO.OUT)
RPi.GPIO.output(_ORP_RELAY_PIN, RPi.GPIO.HIGH)
RPi.GPIO.output(_TEMP_RELAY_PIN, RPi.GPIO.HIGH)

# ----------------------- DISSOLVED OXYGEN FUNCTIONS


def read_orp():
    voltage = _ADC.read_adc(_ORP_SENSOR_PIN, gain=_GAIN) / \
        32767.0 * _ORP_REFERENCE_VOLTAGE
    if not voltage:
        print(
            f'\nWARNING: UNABLE TO READ VOLTAGE FROM ORP SENSOR ON PIN {_ORP_SENSOR_PIN}\n')
        return 0.0
    return ((voltage - _ORP_ZERO_VOLTAGE) / _ORP_SLOPE) - 480

# def read_orp():
#     voltage = _ADC.read_adc(_ORP_SENSOR_PIN, gain=_GAIN) / \
#         32767.0 * _ORP_REFERENCE_VOLTAGE / 1000
#     orp_mv = (2.5 - voltage) / 1.037 * 1000.0  # * 1000 to get mV
#     return orp_mv


def orp_relay(activate):
    if activate:
        RPi.GPIO.output(_ORP_RELAY_PIN, RPi.GPIO.LOW)
        print(f'\tBUBBLER: ON')
    else:
        RPi.GPIO.output(_ORP_RELAY_PIN, RPi.GPIO.HIGH)
        print(f'\tBUBBLER: OFF')

# ----------------------- PH FUNCTIONS


# def read_ph(temperature):
    # del temperature  # deg C
def read_ph():
    # pH calculation formula based on Nernstian response
    voltage = _ADC.read_adc(_PH_SENSOR_PIN, gain=_GAIN) / \
        32767.0 * _PH_REFERENCE_VOLTAGE
    if not voltage:
        print(
            f'\nWARNING: UNABLE TO READ VOLTAGE FROM PH SENSOR ON PIN {_PH_SENSOR_PIN}\n')
        return 0.0
    return (_PH_NEUTRAL_VOLTAGE - voltage) / _PH_SLOPE


def ph_calibration(voltage, temperature):
    del voltage
    del temperature  # deg C
    # calibrating with known pH buffers
    pass

# ----------------------- TEMPERATURE FUNCTIONS


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


def temp_relay(activate):
    if activate:
        RPi.GPIO.output(_TEMP_RELAY_PIN, RPi.GPIO.LOW)
        print(f'\tHEATER: ON')
    else:
        RPi.GPIO.output(_TEMP_RELAY_PIN, RPi.GPIO.HIGH)
        print(f'\tHEATER: OFF')


def read_average(num_readings, read_func):
    total = 0
    for _ in range(num_readings):
        total += read_func()
        time.sleep(0.01)
    return total / num_readings

# ----------------------- DATABASE DEFINTIONS
# TODO: Define as apart of common utils to be included as a submodule for each fish project
Base = declarative_base()


class Measurement(Base):
    __abstract__ = True
    id = Column(Integer, primary_key=True)
    reported_value = Column(Float, nullable=True)
    set_value = Column(Float, nullable=True)
    timestamp = Column(
        DateTime, default=datetime.datetime.now(datetime.timezone.utc))

    @classmethod
    def create_with_last_known(cls, session):
        last_record = session.query(cls).order_by(cls.timestamp.desc()).first()
        if last_record:
            set_value = last_record.set_value
        else:
            set_value = 0.0

        return cls(set_value=set_value)


class Temperature(Measurement):
    __tablename__ = 'temperatures'

    @classmethod
    def create_with_last_known(cls, session):
        return super().create_with_last_known(session)


class PH(Measurement):
    __tablename__ = 'ph_levels'

    @classmethod
    def create_with_last_known(cls, session):
        return super().create_with_last_known(session)


class DissolvedOxygen(Measurement):
    __tablename__ = 'dissolved_oxygen_levels'

    @classmethod
    def create_with_last_known(cls, session):
        return super().create_with_last_known(session)


# ALERT INFO:
# Types: 0 = Temp, 1 = pH, 2 = ORP, 3 = Fish Health
class Alert(Base):
    __tablename__ = 'alerts'
    id = Column(Integer, primary_key=True)
    type = Column(Integer, nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(String(200), nullable=True)
    timestamp = Column(
        DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    read = Column(Boolean, default=False)


# Set up the database engine
engine = create_engine(
    'sqlite:///../fish-flask-app/instance/values.db', echo=False)
Base.metadata.create_all(engine)

# Create a session to interact with the database
Session = sessionmaker(bind=engine)


@contextmanager
def session_scope():
    session = Session()
    try:
        yield session
    finally:
        session.close()


def create_alert(session, alert_type, title, description):
    timestamp = datetime.datetime.now(datetime.timezone.utc)

    alert_entry = Alert(
        type=alert_type,
        title=title,
        description=description,
        timestamp=timestamp
    )
    session.add(alert_entry)


def create_data_entry(session, db_class, value, threshold, alert_type, data_type):
    timestamp = datetime.datetime.now(datetime.timezone.utc)

    data_entry = db_class.create_with_last_known(session)
    data_entry.reported_value = value
    data_entry.timestamp = timestamp
    session.add(data_entry)

    # Only Generate a Single Unset Alert
    if (data_entry.set_value == 0.0 or data_entry.set_value is None) and not _UNSET_STATES[data_type]:
        create_alert(session, alert_type, f"{data_type} Alert",
                     f'User has not specified set {data_type.lower()}.')
        _UNSET_STATES[data_type] = True
    elif data_entry.set_value != 0.0 and data_entry.set_value is not None:
        # Only Generate a Single Threshold Alert until Vitals Recover
        if (not _ALERT_STATES[data_type] and
                abs(data_entry.reported_value - data_entry.set_value) > threshold):
            _ALERT_STATES[data_type] = True
            create_alert(session, alert_type, f"{data_type} Alert",
                         f'The {data_type.lower()} difference exceeded the threshold.\nReported: {data_entry.reported_value}\nSet: {data_entry.set_value}\nThreshold: {threshold}.')
        elif (_ALERT_STATES[data_type] and
              abs(data_entry.reported_value - data_entry.set_value) <= threshold):
            _ALERT_STATES[data_type] = False

        if alert_type == 0:
            temp_relay(data_entry.reported_value < data_entry.set_value)
        elif alert_type == 2:
            orp_relay(data_entry.reported_value < data_entry.set_value)


def database_insertion(temp, orp, pH):
    with session_scope() as session:
        create_data_entry(session, Temperature, temp,
                          _TEMP_THRESHOLD, 0, "Temperature")
        create_data_entry(session, PH, pH, _PH_THRESHOLD, 1, "pH")
        create_data_entry(session, DissolvedOxygen, orp,
                          _ORP_THRESHOLD, 2, "Oxygen")
        session.commit()


def main():
    try:
        # temperature_threshold = float(input("Temperature Threshold (in °F): "))
        while True:
            temp_f = read_temp()
            orp = read_average(500, read_orp)
            pH = read_average(10, read_ph)
            # pH = read_ph((temp_f - 32) * (5.0 / 9.0))

            print(f'TEMP READING: {temp_f:.2f} °F')
            print(f'ORP READING: {orp:.2f} mV')
            print(f'PH READING: {pH:.2f} pH')

            database_insertion(round(temp_f, 2), round(orp, 2), round(pH, 2))

            print()

            lcd = CharLCD(i2c_expander='PCF8574', address=0x27,
                          port=1, cols=20, rows=4, dotsize=8)
            lcd.clear()

            lcd.cursor_pos = (0, 0)

            lcd.write_string(
                f'TEMP: {temp_f:.1f} dF {"ALERT!" if _ALERT_STATES["Temperature"] else ""}\n\r')
            lcd.write_string(
                f'ORP: {orp:.1f} mV {"ALERT!" if _ALERT_STATES["Oxygen"] else ""}\n\r')
            lcd.write_string(
                f'PH:    {pH:.1f} pH {"ALERT!" if _ALERT_STATES["pH"] else ""}\n\r')

            # TODO: find a reasonable value to increase this to (no need to flood database)
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nINFO: KEYBOARD INTERRUPT DETECTED - SHUTTING DOWN\n")

    finally:
        RPi.GPIO.cleanup()

    return 0


if __name__ == '__main__':
    main()
