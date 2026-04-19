import os
import asyncio
import feedparser
import yt_dlp
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# --- SECURE CONFIGURATION (RAILWAY VARIABLES) ---
# The script will pull these directly from Railway's environment variables.
API_ID = int(os.environ.get("API_ID", 0)) 
API_HASH = os.environ.get("API_HASH", "") 
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", 0))

# Channels list separated by commas in Railway
YT_CHANNELS_ENV = os.environ.get("YT_CHANNEL_IDS", "")
YT_CHANNEL_IDS = [cid.strip() for cid in YT_CHANNELS_ENV.split(",") if cid.strip()]

# --- SYSTEM VARIABLES ---
HISTORY_FILE = "history.txt"
CHECK_INTERVAL = 300  # Radar sweep every 5 minutes

# Initialize Telegram MTProto Client
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

def load_history():
    """Loads previously processed target IDs to prevent duplicate strikes."""
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r") as f:
        return set(f.read().splitlines())

def save_history(video_id):
    """Logs target ID to local memory."""
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{video_id}\n")

def download_short(video_url):
    """Validates duration and extracts the payload."""
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            duration = info.get('duration', 0)
            
            # Filter: Only engage targets 65 seconds or shorter
            if duration > 65:
                print(f"Skipped: '{info['title']}' is {duration}s long (Not a Short).")
                return None, None
            
            print(f"Downloading payload: {info['title']}")
            ydl.download([video_url])
            return f"{info['id']}.mp4", info['title']
            
        except Exception as e:
            print(f"Error processing target {video_url}: {e}")
            return None, None

async def main():
    if not SESSION_STRING or not API_ID or not API_HASH:
        print("CRITICAL ERROR: Environment variables missing. Halting execution.")
        return

    print("NEWSBOT Core Online. Establishing secure link to Telegram...")
    await client.connect()
    print(f"Radar active. Monitoring {len(YT_CHANNEL_IDS)} target channels...")

    while True:
        try:
            history = load_history()

            # Sweep each channel
            for channel_id in YT_CHANNEL_IDS:
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                feed = feedparser.parse(rss_url)

                # Process oldest unread first
                for entry in reversed(feed.entries):
                    # Robust extraction of the YouTube video ID
                    video_id = getattr(entry, 'yt_videoid', None)
                    if not video_id and hasattr(entry, 'id'):
                        video_id = entry.id.replace('yt:video:', '')
                        
                    if not video_id:
                        continue
                        
                    video_url = entry.link
                    title = entry.title

                    if video_id not in history:
                        print(f"New target acquired [{channel_id}]: {title}")
                        
                        filepath, vid_title = download_short(video_url)
                        
                        if filepath and os.path.exists(filepath):
                            print("Transmitting payload to Telegram...")
                            await client.send_file(
                                TARGET_CHAT,
                                filepath,
                                caption=f"**{vid_title}**\n\n[Source URL]({video_url})",
                                parse_mode='md'
                            )
                            os.remove(filepath)
                            print("Transmission complete. Local sector cleared.")
                        
                        # Log it to prevent retrying a failed/skipped target
                        save_history(video_id) 

        except Exception as e:
            print(f"System error in main loop: {e}")
            
        print(f"Sweep complete. Entering standby for {CHECK_INTERVAL} seconds...")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    client.loop.run_until_complete(main())