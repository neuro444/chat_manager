import requests
import time
import json

API_URL = "http://127.0.0.1:8000/chat"

def run_chat(name, phone, turns):
    print(f"\n{'='*60}\nStarting Chat: {name}\n{'='*60}")
    session_id = None
    
    for i, text in enumerate(turns):
        print(f"\n[Turn {i+1}] User: {text}")
        resp = requests.post(API_URL, json={
            "user_id": phone,
            "session_id": session_id,
            "message": text,
            "include_llm_debug": True
        }).json()
        
        session_id = resp.get("session_id")
        answer = resp.get('answer')
        print(f"[Turn {i+1}] Assistant: {answer}")
        
        tools = resp.get("tools_called")
        if tools:
            print(f"   --> Tools Called: True (Order Priced)")
        
        order = resp.get("order")
        if order:
            print(f"   --> INTERNAL ORDER CREATED! Customer Name Saved: '{order.get('customer_name')}'")
            print(f"   --> FINAL ITEMS: {[item['name'] + ' x' + str(item['quantity']) for item in order.get('items', [])]}")

if __name__ == "__main__":
    print("Waiting for API...")
    for _ in range(15):
        try:
            requests.get("http://127.0.0.1:8000/health")
            break
        except:
            time.sleep(1)

    run_chat("Chat 1: Simple Add", "+15550001111", [
        "Hi, my name is John. I want 1 Veg Biriyani.",
        "Actually, please add 2 Samosas to that.",
        "That's everything, for pickup."
    ])

    run_chat("Chat 2: Replace/Remove", "+15550002222", [
        "Hello, this is Sarah. I'd like 2 Chicken Tikka Masala and 2 Butter Naan.",
        "Change my mind, remove 1 Chicken Tikka Masala.",
        "Okay, I'm ready to order for pickup."
    ])

    run_chat("Chat 3: Delayed Name", "+15550003333", [
        "I want 1 Mango Lassi.",
        "My name is Mike. Also, I want to add a Samosa.",
        "That's all, for pickup."
    ])
