
import sys
import os
import json
sys.path.append(os.getcwd())

try:
    from history_manager import HistoryManager
    
    print("Initializing HistoryManager...")
    mgr = HistoryManager()
    
    # 1. Create Session
    sid = mgr.create_session("Test Session")
    print(f"✅ Session Created: ID={sid}")
    
    # 2. Save Message
    mgr.save_message(sid, "user", "Hello History")
    mgr.save_message(sid, "ai", "I remember everything", meta={"type": "chart"})
    print("✅ Messages Saved")
    
    # 3. Retrieve
    msgs = mgr.get_session_messages(sid)
    print(f"✅ Retrieved {len(msgs)} messages")
    print(f"   Last Msg Meta: {msgs[-1]['meta']}")
    
    # 4. File Archive
    files = mgr.get_archived_files()
    print(f"✅ Archive Scanned: Found {sum(len(v) for v in files.values())} files across {len(files)} categories.")

except Exception as e:
    print(f"❌ Verification Failed: {e}")
