# test_fyers_token.py
"""
Minimal script to test Fyers API authentication using your current token and app_id.
Run this after updating your token to verify it works independently of your main app.
"""
import json
import os
import sys
from fyers_apiv3 import fyersModel

def load_token():
    # Try fyers_token.txt first
    if os.path.exists('fyers_token.txt'):
        with open('fyers_token.txt') as f:
            token = f.read().strip()
            if token:
                return token
    # Try fyers_tokens.json
    if os.path.exists('fyers_tokens.json'):
        with open('fyers_tokens.json') as f:
            data = json.load(f)
            if 'access_token' in data:
                return data['access_token']
    print('No token found in fyers_token.txt or fyers_tokens.json')
    sys.exit(1)

def main():
    app_id = os.environ.get('FYERS_APP_ID') or input('Enter your Fyers APP_ID: ')
    access_token = load_token()
    print(f'Using APP_ID: {app_id}')
    print(f'Using ACCESS_TOKEN: {access_token[:10]}...')
    session_token = f"{app_id}:{access_token}"
    fyers = fyersModel.FyersModel(client_id=app_id, token=session_token, log_path=None)
    # Try a simple API call
    try:
        resp = fyers.get_profile()
        print('API Response:', resp)
        if resp.get('s') == 'ok':
            print('SUCCESS: Token is valid and authenticated.')
        else:
            print('FAIL: Token is invalid or not authenticated.')
    except Exception as e:
        print('Exception during API call:', e)

if __name__ == '__main__':
    main()
