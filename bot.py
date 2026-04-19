import os
import asyncio
import feedparser
import yt_dlp
import instaloader
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# --- SECURE CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 0)) 
API_HASH = os.environ.get("API_HASH", "") 
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", 0))

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
ig_radar = instaloader.Instaloader(quiet=True, download_video_thumbnails=False, save_metadata=False)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r") as f:
        return set(f.read().splitlines())

def save_history(video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{video_id}\n")

def download_video(video_url):
    """Universal downloader for YT and IG payloads."""
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
            
            # Duration limit only for YT. IG Reels are natively short.
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
    """Executes YouTube Radar Sweep."""
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
    """Executes Instagram Radar Sweep."""
    for ig_user in IG_USERNAMES:
        try:
            profile = instaloader.Profile.from_username(ig_radar.context, ig_user)
            post_iterator = profile.get_posts()
            
            # Scan only the 3 most recent posts to avoid triggering IG anti-bot defenses
            for i in range(3):
                try:
                    post = next(post_iterator)
                except StopIteration:
                    break
                
                if post.is_video:
                    # Prefix IG ids so they don't collide with YT ids
                    video_id = f"ig_{post.shortcode}"
                    
                    if video_id not in history:
                        url = f"https://www.instagram.com/reel/{post.shortcode}/"
                        print(f"New IG target [{ig_user}]: {post.shortcode}")
                        
                        filepath, vid_title = download_video(url)
                        
                        if filepath and os.path.exists(filepath):
                            await client.send_file(
                                TARGET_CHAT, filepath,
                                caption=f"**Instagram Reel: @{ig_user}**\n\n[Instagram Source]({url})",
                                parse_mode='md'
                            )
                            os.remove(filepath)
                        save_history(video_id)
                        history.add(video_id)
        except Exception as e:
            # IG will likely throw 429 errors (Too Many Requests). We catch it so YT keeps working.
            print(f"IG Sweep Error on {ig_user}: {e}")

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
