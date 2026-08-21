import requests
import time
import json
import uuid

API_URL = "http://127.0.0.1:8000/chat"

def run_order(test_name, user_id, turns):
    print(f"\n{'='*50}\nStarting Test: {test_name}\n{'='*50}")
    session_id = None
    
    for i, message in enumerate(turns):
        print(f"\n--- Turn {i+1} ---")
        print(f"User: {message}")
        
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message
        }
        
        try:
            resp = requests.post(API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            session_id = data.get("session_id")
            
            print(f"Assistant: {data.get('answer')}")
            
            # Print significant flags
            flags = []
            if data.get("order_ready"): flags.append("ORDER_READY=True")
            if data.get("call_ended"): flags.append("CALL_ENDED=True")
            if data.get("To_manager"): flags.append("TO_MANAGER=True")
            if flags:
                print(f"Flags: {', '.join(flags)}")
                
            if data.get("order"):
                print(f"Order Object:")
                print(json.dumps(data.get("order"), indent=2))
                
            if data.get("summary"):
                print(f"Handoff Summary: {data.get('summary')}")
                
        except Exception as e:
            print(f"Error during request: {e}")
            break
            
    print("\n[End of Test]")

if __name__ == "__main__":
    # Wait for API to be available
    print("Waiting for API...")
    for _ in range(10):
        try:
            requests.get("http://127.0.0.1:8000/health")
            break
        except requests.exceptions.ConnectionError:
            time.sleep(1)
    else:
        print("API failed to start.")
        exit(1)

    print("API is up!")

    # Test 1: Simple Pickup
    run_order(
        "Order 1 - Simple Pickup",
        user_id="+15550000001",
        turns=[
            "Hi, I'd like 2 Samosas and 1 Veg Biriyani for pickup.",
            "My name is Alice. That's everything."
        ]
    )

    # Test 2: Manager Handoff (Catering)
    run_order(
        "Order 2 - Catering (Manager Handoff)",
        user_id="+15550000002",
        turns=[
            "Hi, I need catering for an office party of 50 people next Friday. My name is Bob.",
            "Yes, that is correct. You can send it to the manager."
        ]
    )

    # Test 3: Pickup with Changes
    run_order(
        "Order 3 - Pickup with Modifications",
        user_id="+15550000003",
        turns=[
            "I'd like 1 Chicken Tikka Masala for pickup, under Charlie.",
            "Actually, change that to 2 Chicken Tikka Masala and add 1 Butter Naan.",
            "That's all, I'm ready to finish."
        ]
    )
