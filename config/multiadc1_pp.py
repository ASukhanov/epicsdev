"""Pypet definition for device multiadc1"""
import multiadc_pp as module

def PyPage(**_):
    return  module.PyPage(instance='multiadc1:', title='multiadc1',
        channels=6)
