#!/usr/bin/env python3
"""
Tool to exchange short-lived Facebook User Access Token + App Secret
into a Never-Expiring Page Access Token.
"""
import sys
import json
import requests

def exchange_token(app_id: str, app_secret: str, user_token: str, page_id: str):
    print("[*] Exchanging for long-lived user token...")
    exchange_url = "https://graph.facebook.com/v19.0/oauth/access_token"
    res1 = requests.get(exchange_url, params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": user_token
    }).json()

    if "access_token" not in res1:
        print(f"[-] Failed to get long-lived user token: {res1}")
        sys.exit(1)

    long_user_token = res1["access_token"]
    print("[+] Long-lived user token obtained.")

    print(f"[*] Fetching permanent Page Access Token for Page ID: {page_id}...")
    page_url = f"https://graph.facebook.com/v19.0/{page_id}"
    res2 = requests.get(page_url, params={
        "fields": "access_token,name",
        "access_token": long_user_token
    }).json()

    if "access_token" not in res2:
        print(f"[-] Failed to get page access token: {res2}")
        sys.exit(1)

    perm_page_token = res2["access_token"]
    page_name = res2.get("name", "Unknown Page")
    print(f"[+] Page: {page_name}")

    print("[*] Verifying token expiry with debug_token...")
    debug_url = "https://graph.facebook.com/debug_token"
    debug_res = requests.get(debug_url, params={
        "input_token": perm_page_token,
        "access_token": perm_page_token
    }).json()

    expires_at = debug_res.get("data", {}).get("expires_at")
    is_valid = debug_res.get("data", {}).get("is_valid")
    print(f"[+] Token valid: {is_valid}, Expires at: {expires_at} (0 = Never Expire)")

    config = {
        "page_id": page_id,
        "page_name": page_name,
        "page_token": perm_page_token
    }

    with open("fb_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print("[+] Saved to fb_config.json successfully!")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python3 exchange_token.py <APP_ID> <APP_SECRET> <SHORT_USER_TOKEN> <PAGE_ID>")
        sys.exit(1)

    exchange_token(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
