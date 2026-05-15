# paths.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime_data")

ACCESS_TOKEN_FILE = os.path.join(RUNTIME_DIR, "access_token.txt")
INSTRUMENTS_FILE = os.path.join(RUNTIME_DIR, "instruments.json")

