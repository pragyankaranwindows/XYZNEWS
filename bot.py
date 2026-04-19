import os
import asyncio
import feedparser
import requests
import yt_dlp
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# --- SECURE CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 0)) 
API_HASH = os.environ.get("API_HASH", "") 
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", 0))

# Proxy Integration
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

# Target Arrays
YT_CHANNELS_ENV = os.environ.get("YT_CHANNEL_IDS", "")
YT_CHANNEL_IDS = [cid.strip() for cid in YT_CHANNELS_ENV.split(",") if cid.strip()]

IG_USERS_ENV = os.environ.get("IG_USERNAMES", "")
IG_USERNAMES = [user.strip() for user in IG_USERS_ENV.split(",") if user.strip()]

# --- SYSTEM VARIABLES ---
HISTORY_FILE = "history.txt"
CHECK_INTERVAL = 300  # 5 minutes

# Initialize Systems
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r") as f:
        return set(f.read().splitlines())

def save_history(video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{video_id}\n")

def download_video(video_url):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            duration = info.get('duration', 0)
            title = info.get('title', 'Video Payload')
            
            if 'youtube' in video_url and duration > 65:
                print(f"Skipped: '{title}' is {duration}s long (Not a Short).")
                return None, None
            
            print(f"Downloading payload...")
            ydl.download([video_url])
            return f"{info['id']}.mp4", title
            
        except Exception as e:
            print(f"Extraction error for {video_url}: {e}")
            return None, None

async def sweep_youtube(history):
    for channel_id in YT_CHANNEL_IDS:
        try:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            feed = feedparser.parse(rss_url)

            for entry in reversed(feed.entries):
                video_id = getattr(entry, 'yt_videoid', None)
                if not video_id and hasattr(entry, 'id'):
                    video_id = entry.id.replace('yt:video:', '')
                    
                if not video_id or video_id in history:
                    continue

                print(f"New YT target [{channel_id}]: {entry.title}")
                filepath, vid_title = download_video(entry.link)
                
                if filepath and os.path.exists(filepath):
                    await client.send_file(
                        TARGET_CHAT, filepath,
                        caption=f"**{vid_title}**\n\n[YouTube Source]({entry.link})",
                        parse_mode='md'
                    )
                    os.remove(filepath)
                save_history(video_id)
                history.add(video_id)
        except Exception as e:
            print(f"YT Sweep Error on {channel_id}: {e}")

async def sweep_instagram(history):
    if not RAPIDAPI_KEY:
        print("Skipping IG Sweep: RAPIDAPI_KEY not set.")
        return

    url = "https://instagram-scraper-stable-api.p.rapidapi.com/get_ig_user_reels.php"
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-host": "instagram-scraper-stable-api.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    for ig_user in IG_USERNAMES:
        try:
            payload = {
                "username_or_url": ig_user,
                "amount": "3",  
                "pagination_token": ""
            }
            
            response = requests.post(url, data=payload, headers=headers)
            
            if response.status_code != 200:
                print(f"Proxy Error [{response.status_code}] for {ig_user}.")
                continue
                
            data = response.json()
            
            items = data.get('reels', [])
            if not items and 'data' in data:
                items = data['data']
            elif not items and 'items' in data:
                items = data['items']
            elif not items and isinstance(data, list):
                items = data
                
            if not items:
                print(f"No reels found for {ig_user}. Raw keys: {list(data.keys())}")
                continue

            count = 0
            for item in items:
                if count >= 3:
                    break
                
                node = item.get('node', item)
                
                # We check multiple common identifiers
                shortcode = node.get('shortcode') or node.get('code') or node.get('id') or node.get('media_id')
                
                if not shortcode:
                    # DIAGNOSTIC TRIGGER: If we still can't find it, print exactly what is inside the node
                    print(f"DEBUG [{ig_user}]: Missing shortcode identifier. Available keys in this reel are: {list(node.keys())}")
                    continue

                # Clean up ID if it has extra tracking tags
                if '_' in str(shortcode):
                    shortcode = str(shortcode).split('_')[0]

                video_id = f"ig_{shortcode}"
                
                if video_id not in history:
                    reel_url = f"https://www.instagram.com/reel/{shortcode}/"
                    print(f"New IG target [{ig_user}]: {shortcode}")
                    
                    filepath, vid_title = download_video(reel_url)
                    
                    if filepath and os.path.exists(filepath):
                        await client.send_file(
                            TARGET_CHAT, filepath,
                            caption=f"**Instagram Reel: @{ig_user}**\n\n[Instagram Source]({reel_url})",
                            parse_mode='md'
                        )
                        os.remove(filepath)
                    save_history(video_id)
                    history.add(video_id)
                
                count += 1
                
        except Exception as e:
            print(f"IG Proxy Routine Error on {ig_user}: {e}")

async def main():
    if not SESSION_STRING or not API_ID or not API_HASH:
        print("CRITICAL ERROR: Keys missing. Halting.")
        return

    print("NEWSBOT Advanced Core Online.")
    await client.connect()

    while True:
        history = load_history()
        
        print(f"\n--- Initiating Radar Sweep ---")
        if YT_CHANNEL_IDS:
            await sweep_youtube(history)
        if IG_USERNAMES:
            await sweep_instagram(history)
            
        print(f"Sweep complete. Entering standby for {CHECK_INTERVAL} seconds...")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    client.loop.run_until_complete(main())
