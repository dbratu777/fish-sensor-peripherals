import datetime
import glob
import os
import time
import RPi.GPIO

from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

_FEEDER_RELAY_PIN = 25

RPi.GPIO.setmode(RPi.GPIO.BCM)
RPi.GPIO.setup(_FEEDER_RELAY_PIN, RPi.GPIO.OUT)
RPi.GPIO.output(_FEEDER_RELAY_PIN, RPi.GPIO.HIGH)

Base = declarative_base()


class Feeder(Base):
    __tablename__ = 'feeder'
    id = Column(Integer, primary_key=True)
    interval = Column(Integer, default=0, nullable=False)
    feed = Column(Boolean, default=False)
    timestamp = Column(DateTime)

    @classmethod
    def create_with_last_known(cls, session):
        last_record = session.query(cls).order_by(cls.timestamp.desc()).first()
        if last_record:
            interval = last_record.interval
            feed = last_record.feed
        else:
            interval = 0
            feed = False

        return cls(interval=interval, feed=feed)


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


def feeder_relay():
    RPi.GPIO.output(_FEEDER_RELAY_PIN, RPi.GPIO.LOW)
    time.sleep(0.5)
    RPi.GPIO.output(_FEEDER_RELAY_PIN, RPi.GPIO.HIGH)


def activate_feeder():
    with session_scope() as session:
        timestamp = datetime.datetime.now(datetime.timezone.utc)

        data_entry = Feeder.create_with_last_known(session)
        data_entry.timestamp = timestamp

        if data_entry.feed:
            feeder_relay()

            data_entry.feed = False
            session.add(data_entry)
            session.commit()

        return data_entry.interval


def main():
    wait_time = 5   # (s)
    scale = 3600    # 1 hr in s
    try:
        interval = activate_feeder() * scale
        time_till_feed = interval
        while True:
            temp_interval = activate_feeder() * scale
            if interval != temp_interval:
                interval = temp_interval
                time_till_feed += interval - temp_interval
            if time_till_feed <= 0 and interval != 0:
                feeder_relay()
                time_till_feed = interval

            time_till_feed -= wait_time
            time.sleep(wait_time)

    except KeyboardInterrupt:
        print("\nINFO: KEYBOARD INTERRUPT DETECTED - SHUTTING DOWN\n")

    finally:
        RPi.GPIO.cleanup()

    return 0


if __name__ == '__main__':
    main()
