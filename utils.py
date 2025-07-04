import random
import string
import requests
from bitcoinlib.wallets import Wallet

def generate_deal_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def validate_amount(input_str):
    try:
        amount = float(input_str.replace('$', '').strip())
        return amount if amount >= 0.1 else None
    except ValueError:
        return None

def get_live_rate():
    response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd")
    return response.json()["litecoin"]["usd"]

def format_progress(confirmations):
    progress = min(confirmations, 6)
    return "🟩" * progress + "⬜" * (6 - progress)

def get_ltc_address():
    with open('ltcaddy.txt') as f:
        return f.read().strip()

def get_wif_key():
    with open('wifkey.txt') as f:
        return f.read().strip()

def send_ltc(receiver, amount, wif_key):
    wallet = Wallet.import_key("mm_bot", wif_key, network='litecoin')
    tx = wallet.send_to(receiver, amount, fee=0.0001)
    return tx.txid

def validate_ltc_address(address):
    return address.startswith(('L', 'M', 'ltc1')) and 26 <= len(address) <= 48
