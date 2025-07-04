import requests

def check_payment(ltc_address, expected_amount):
    """
    Check for payments to an LTC address using SoChain API
    Returns payment details if found, None otherwise
    """
    try:
        response = requests.get(
            f"https://sochain.com/api/v2/address/LTC/{ltc_address}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        for tx in data["data"]["txs"]:
            # Compare amounts with 8 decimal precision
            if abs(float(tx["value"]) - expected_amount) < 0.00000001:
                return {
                    "txid": tx["txid"],
                    "amount": float(tx["value"]),
                    "confirmations": int(tx["confirmations"]),
                    "time": tx["time"]
                }
        return None
    except Exception as e:
        print(f"Payment check failed: {e}")
        return None

def get_transaction_status(txid):
    """
    Get detailed transaction status
    """
    try:
        response = requests.get(
            f"https://sochain.com/api/v2/tx/LTC/{txid}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return {
            "confirmations": data["data"]["confirmations"],
            "block": data["data"]["block_no"],
            "status": "confirmed" if data["data"]["confirmations"] >= 6 else "pending"
        }
    except Exception as e:
        print(f"Transaction check failed: {e}")
        return None
