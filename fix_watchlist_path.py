"""
FIX WATCHLIST PATH - Run this ONCE to fix the path issue
=========================================================
This fixes the bug where FPB was reading old watchlist data.

Run: python fix_watchlist_path.py
"""

import os

# Path to fix
FPB_FILE = "C:/Users/Hassan/ORB-Bot/fpb_strategy.py"

# Old code (wrong order - checks scanners/ first)
OLD_CODE = '''    possible_paths = [
        watchlist_path,
        "C:/Users/Hassan/ORB-Bot/scanners/output/watchlist.json",
        "./scanners/output/watchlist.json",
        "./output/watchlist.json",
        "../scanners/output/watchlist.json",
    ]'''

# New code (correct order - checks output/ first)
NEW_CODE = '''    possible_paths = [
        watchlist_path,
        "C:/Users/Hassan/ORB-Bot/output/watchlist.json",           # NEW location first!
        "C:/Users/Hassan/ORB-Bot/scanners/output/watchlist.json",  # Old location second
        "./output/watchlist.json",
        "./scanners/output/watchlist.json",
    ]'''

def fix_path():
    print("🔧 Fixing watchlist path in fpb_strategy.py...")
    
    if not os.path.exists(FPB_FILE):
        print(f"❌ File not found: {FPB_FILE}")
        return False
    
    # Read file
    with open(FPB_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already fixed
    if "# NEW location first!" in content:
        print("✅ Already fixed!")
        return True
    
    # Check if old code exists
    if OLD_CODE not in content:
        print("⚠️  Could not find the code to replace.")
        print("   The file may have been modified.")
        print("   Manual fix needed.")
        return False
    
    # Replace
    new_content = content.replace(OLD_CODE, NEW_CODE)
    
    # Backup original
    backup_path = FPB_FILE + ".backup"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"📁 Backup saved: {backup_path}")
    
    # Write fixed file
    with open(FPB_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Fixed! Now fpb_strategy.py will read from output/ first.")
    return True


def also_delete_stale_file():
    """Also delete the stale watchlist in scanners/output/"""
    stale_path = "C:/Users/Hassan/ORB-Bot/scanners/output/watchlist.json"
    
    if os.path.exists(stale_path):
        try:
            os.remove(stale_path)
            print(f"🗑️  Deleted stale file: {stale_path}")
        except:
            print(f"⚠️  Could not delete: {stale_path}")
            print("   Delete it manually in File Explorer")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔧 FPB WATCHLIST PATH FIX")
    print("="*60 + "\n")
    
    if fix_path():
        also_delete_stale_file()
        print("\n✅ All done! The path issue is fixed.")
    else:
        print("\n❌ Fix failed. See messages above.")
    
    print()
