#!/usr/bin/env python3
"""
Test script to verify the username and email validation endpoints
"""

import requests
import json

def test_username_endpoint():
    """Test the username validation endpoint"""
    url = 'http://127.0.0.1:8001/check_username'
    headers = {'Content-Type': 'application/json'}
    
    # Test with a username that likely doesn't exist
    test_data = {'username': 'testuser12345'}
    
    try:
        response = requests.post(url, headers=headers, json=test_data)
        print(f"Username endpoint status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"Error response: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing username endpoint: {e}")
        return False

def test_email_endpoint():
    """Test the email validation endpoint"""
    url = 'http://127.0.0.1:8001/check_email'
    headers = {'Content-Type': 'application/json'}
    
    # Test with an email that likely doesn't exist
    test_data = {'email': 'test12345@example.com'}
    
    try:
        response = requests.post(url, headers=headers, json=test_data)
        print(f"Email endpoint status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"Error response: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing email endpoint: {e}")
        return False

if __name__ == '__main__':
    print("Testing validation endpoints...\n")
    
    print("1. Testing username validation:")
    username_ok = test_username_endpoint()
    
    print("\n2. Testing email validation:")
    email_ok = test_email_endpoint()
    
    print("\n" + "="*50)
    if username_ok and email_ok:
        print("✅ Both endpoints are working correctly!")
    else:
        print("❌ Some endpoints are not working properly.")
        if not username_ok:
            print("   - Username validation failed")
        if not email_ok:
            print("   - Email validation failed")