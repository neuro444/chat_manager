import requests
import time
import json

API_URL = "http://127.0.0.1:8000/chat"

def run_test(test_name, user_id, turns):
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
                
        except Exception as e:
            print(f"Error during request: {e}")
            break
            
    print("\n[End of Test]")

if __name__ == "__main__":
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

    # Test 1: Vague Catering Request (Should NOT interrogate)
    run_test(
        "Test 1 - Vague Catering Request",
        user_id="+15551111111",
        turns=[
            "I'd like to order catering for an event."
        ]
    )

    # Test 2: Vague Cake Request (Should NOT interrogate)
    run_test(
        "Test 2 - Vague Custom Cake Request",
        user_id="+15552222222",
        turns=[
            "I want to get a custom cake made for my son's birthday."
        ]
    )

    # Test 3: Direct Request for Manager (Should NOT ask why)
    run_test(
        "Test 3 - Direct Manager Request",
        user_id="+15553333333",
        turns=[
            "Can you just connect me to the manager please?"
        ]
    )

    # Test 4: Follow up refusal to give details (Stress test)
    run_test(
        "Test 4 - Catering Request with Immediate Manager Escalate",
        user_id="+15554444444",
        turns=[
            "I am looking for some catering.",
            "I don't know the details yet, just transfer me to the manager so I can talk to them."
        ]
    )
