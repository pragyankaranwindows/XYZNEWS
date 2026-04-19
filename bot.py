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

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

YT_CHANNELS_ENV = os.environ.get("YT_CHANNEL_IDS", "")
YT_CHANNEL_IDS = [cid.strip() for cid in YT_CHANNELS_ENV.split(",") if cid.strip()]

IG_USERS_ENV = os.environ.get("IG_USERNAMES", "")
IG_USERNAMES = [user.strip() for user in IG_USERS_ENV.split(",") if user.strip()]

HISTORY_FILE = "history.txt"
CHECK_INTERVAL = 300  

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
    """Used strictly for YouTube targets."""
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            if 'youtube' in video_url and info.get('duration', 0) > 65:
                return None, None
            ydl.download([video_url])
            return f"{info['id']}.mp4", info.get('title', 'Video Payload')
        except Exception as e:
            print(f"YT Extraction error: {e}")
            return None, None

def download_direct(url, filename):
    """Bypasses yt-dlp to download directly from Meta's CDN."""
    try:
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return filename
        return None
    except Exception as e:
        print(f"Direct download failed: {e}")
        return None

async def sweep_youtube(history):
    for channel_id in YT_CHANNEL_IDS:
        try:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            feed = feedparser.parse(rss_url)

            for entry in reversed(feed.entries):
                video_id = getattr(entry, 'yt_videoid', None) or entry.id.replace('yt:video:', '')
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
            pass

async def sweep_instagram(history):
    if not RAPIDAPI_KEY: return

    url = "https://instagram-scraper-stable-api.p.rapidapi.com/get_ig_user_reels.php"
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-host": "instagram-scraper-stable-api.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    for ig_user in IG_USERNAMES:
        try:
            payload = {"username_or_url": ig_user, "amount": "3", "pagination_token": ""}
            response = requests.post(url, data=payload, headers=headers)
            if response.status_code != 200: continue
                
            data = response.json()
            items = data.get('reels', []) or data.get('data', []) or data.get('items', []) or (data if isinstance(data, list) else [])
            
            count = 0
            for item in items:
                if count >= 3: break
                
                node = item.get('node', item)
                media = node.get('media', node)
                shortcode = media.get('code') or media.get('shortcode') or node.get('code') or node.get('shortcode')
                
                if not shortcode: continue
                if '_' in str(shortcode): shortcode = str(shortcode).split('_')[0]

                video_id = f"ig_{shortcode}"
                
                if video_id not in history:
                    print(f"New IG target [{ig_user}]: {shortcode}")
                    
                    # EXTRACT THE DIRECT CDN LINK
                    cdn_url = media.get('video_url') or node.get('video_url')
                    
                    if not cdn_url:
                        print(f"DEBUG [{ig_user}]: Missing CDN link. Keys inside media are: {list(media.keys())}")
                        save_history(video_id) # Skip it so we don't get stuck
                        continue
                        
                    print(f"Bypassing Meta block. Downloading directly from CDN...")
                    filepath = f"{video_id}.mp4"
                    downloaded_file = download_direct(cdn_url, filepath)
                    
                    if downloaded_file and os.path.exists(downloaded_file):
                        reel_url = f"https://www.instagram.com/reel/{shortcode}/"
                        await client.send_file(
                            TARGET_CHAT, downloaded_file,
                            caption=f"**Instagram Reel: @{ig_user}**\n\n[Instagram Source]({reel_url})",
                            parse_mode='md'
                        )
                        os.remove(downloaded_file)
                        print(f"Payload delivered: {shortcode}")
                        
                    save_history(video_id)
                    history.add(video_id)
                count += 1
        except Exception as e:
            print(f"IG Error on {ig_user}: {e}")

async def main():
    if not SESSION_STRING or not API_ID or not API_HASH:
        print("CRITICAL ERROR: Keys missing. Halting.")
        return

    print("NEWSBOT Advanced Core Online.")
    await client.connect()

    while True:
        history = load_history()
        print(f"\n--- Initiating Radar Sweep ---")
        if YT_CHANNEL_IDS: await sweep_youtube(history)
        if IG_USERNAMES: await sweep_instagram(history)
        print(f"Sweep complete. Entering standby for {CHECK_INTERVAL} seconds...")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    client.loop.run_until_complete(main())
