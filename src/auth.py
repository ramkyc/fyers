import os
import sys
# Add the project root to the Python path to allow absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
import config # config.py is now in the project root

from fyers_apiv3 import fyersModel 
import webbrowser
import json

TOKEN_FILE = "fyers_tokens.json"

def save_tokens(access_token, refresh_token):
    """
    Saves access and refresh tokens to a JSON file.
    """
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, f)

def load_tokens():
    """
    Loads access and refresh tokens from a JSON file.
    """
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None

def refresh_access_token(session_model, refresh_token, fyers_pin):
    """
    Uses a refresh token to get a new access token.
    """
    session_model.set_token(refresh_token)
    response = session_model.generate_token()
    if "access_token" in response:
        save_tokens(response["access_token"], response["refresh_token"])
        return response["access_token"]
    else:
        raise Exception(f"Failed to refresh access token: {response}")

def get_access_token():
    """
    Retrieves the access token from a file.
    Does NOT attempt to refresh or generate a new one.

    Returns:
        str: The access token.

    Raises:
        Exception: If no valid access token is found in the file.
    """
    tokens = load_tokens()
    if tokens and "access_token" in tokens:
        print("Loaded access token from file.")
        return tokens["access_token"]
    else:
        raise Exception("No valid access token found in fyers_tokens.json. Please generate it manually on your local machine.")

def get_fyers_model(raw_access_token):
    """
    Initializes and returns a fyersModel instance with a valid access token.

    Args:
        raw_access_token (str): The raw access token.

    Returns:
        fyersModel: An authenticated fyersModel instance.
    """
    fyers = fyersModel.FyersModel(client_id=config.APP_ID, is_async=False, token=raw_access_token, log_path=config.LOG_PATH)
    return fyers

def get_formatted_access_token(raw_access_token):
    """
    Formats the raw access token for the WebSocket.

    Args:
        raw_access_token (str): The raw access token.

    Returns:
        str: The formatted access token in the format APP_ID:ACCESS_TOKEN.
    """
    return f"{config.APP_ID}:{raw_access_token}"

import argparse

def generate_and_save_tokens_manually(redirected_url=None):
    """
    Performs the manual browser-based authentication flow to generate
    and save access and refresh tokens to fyers_tokens.json.
    If redirected_url is provided, it uses that instead of prompting.
    """
    session = fyersModel.SessionModel(
        response_type="code",
        redirect_uri=config.REDIRECT_URI,
        secret_key=config.SECRET_KEY,
        client_id=config.APP_ID,
        grant_type="authorization_code",
    )

    if redirected_url is None:
        print("Generating new access token via manual authentication...")
        auth_code_url = session.generate_authcode()
        print(f"Visit and login at: {auth_code_url}")
        # In a server environment, you'd copy this URL and open it locally.
        # webbrowser.open(auth_code_url, new=1) # This won't work on a headless server

        redirected_url = input("Paste the full redirected URL here: ")
    else:
        print("Using provided redirected URL to generate tokens...")

    try:
        # Extract auth_code from the URL
        auth_code = redirected_url.split('auth_code=')[1].split('&')[0]
        print(f"DEBUG: Captured auth_code (first 10 chars): {auth_code[:10]}...")
    except IndexError:
        raise Exception("Could not find 'auth_code' in the provided URL. Please make sure you paste the full URL.")

    session.set_token(auth_code)
    response = session.generate_token()
    print(f"DEBUG: Response from generate_token: {response}")

    if "access_token" in response:
        save_tokens(response["access_token"], response["refresh_token"])
        print("Successfully generated and saved access token.")
    else:
        raise Exception(f"Failed to generate access token: {response}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Fyers API tokens.")
    parser.add_argument("--redirect-url", type=str, help="The full redirected URL containing the auth_code after manual login.")
    args = parser.parse_args()

    try:
        generate_and_save_tokens_manually(redirected_url=args.redirect_url)
        fyers = get_fyers_model(get_access_token())
        print("Fyers model initialized successfully.")
        print(f"Profile: {fyers.get_profile()}")
    except Exception as e:
        print(f"An error occurred: {e}")