#!/usr/bin/env python3
import random
import time
import sys

delay = 0.1

while True:
    for _ in range(3):
        print("testsensor {}".format(random.random() * 40))
        print("sensortest {}".format(random.random() * 40))
        print()
        time.sleep(delay)

    print("Sensor Error test", file=sys.stderr)
    print("testsensor {}".format(9001))
    print("sensortest {}".format(random.random() * 40))
    print()
    time.sleep(delay)


    for _ in range(3):
        print("testsensor {}".format(random.random() * 40))
        print("sensortest {}".format(random.random() * 40))
        print()
        time.sleep(delay)

    print("Missing sensor test", file=sys.stderr)
    print("sensortest {}".format(random.random() * 40))
    print()
    time.sleep(delay)

    for _ in range(3):
        print("testsensor {}".format(random.random() * 40))
        print("sensortest {}".format(random.random() * 40))
        print()
        time.sleep(delay)

    print("Extra sensor test", file=sys.stderr)
    print("idonotexist {}".format(random.random() * 40))
    print("testsensor {}".format(random.random() * 40))
    print("sensortest {}".format(random.random() * 40))
    print()
    time.sleep(delay)


    for _ in range(3):
        print("testsensor {}".format(random.random() * 40))
        print("sensortest {}".format(random.random() * 40))
        print()
        time.sleep(delay)

    print("Too Hot Test", file=sys.stderr)
    print("testsensor {}".format(45))
    print("sensortest {}".format(40))
    print()
    time.sleep(delay)

    for _ in range(3):
        print("testsensor {}".format(random.random() * 40))
        print("sensortest {}".format(random.random() * 40))
        print()
        time.sleep(delay)

    print("high diff test", file=sys.stderr)
    print("testsensor {}".format(45))
    print("sensortest {}".format(25))
    print()
    time.sleep(delay)
