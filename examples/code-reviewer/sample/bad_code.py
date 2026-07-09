import os
import sys


def calc(a, b):
    try:
        result = a / b
    except:
        result = None
    return result


class DataProcessor:
    def process(self, data):
        x = 0
        for item in data:
            if item % 2 == 0:
                x += item * 2
            else:
                x -= item
        return x


def very_long_function_name_that_does_little_to_nothing_really_and_should_be_refactored():
    pass
