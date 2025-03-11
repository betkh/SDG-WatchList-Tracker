from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime
import re

# Function to convert ISO 8601 duration to HH:MM:SS


def parse_duration(iso_duration):
    if iso_duration == "N/A":
        return "00:00:00"
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return "00:00:00"
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# Load the API key from API_KEYS.config
load_dotenv("API_KEYS.config")
api_key = os.getenv("API_KEY")
if api_key is None:
    raise ValueError(
        "API_KEY not found in API_KEYS.config! Check the file format.")

# Build the YouTube API client
youtube = build("youtube", "v3", developerKey=api_key)

# Correct Seattle Data Guy channel ID
channel_id = "UCmLGJ3VYBcfRaWbP6JLJcpA"

# Step 1: Get the uploads playlist ID and all playlists
request = youtube.channels().list(
    part="contentDetails",
    id=channel_id
)
response = request.execute()
uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

# Fetch all playlists from the channel
playlists = {}
playlist_request = youtube.playlists().list(
    part="snippet",
    channelId=channel_id,
    maxResults=50
)
while playlist_request:
    response = playlist_request.execute()
    for playlist in response["items"]:
        playlists[playlist["id"]] = playlist["snippet"]["title"]
    playlist_request = youtube.playlists().list_next(playlist_request, response)

# Step 2: Pull video data from uploads playlist
video_data = {}
next_page_token = None

while True:
    playlist_request = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_playlist_id,
        maxResults=50,
        pageToken=next_page_token
    )
    playlist_response = playlist_request.execute()

    for item in playlist_response["items"]:
        video_id = item["snippet"]["resourceId"]["videoId"]
        video_data[video_id] = {
            "title": item["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": item["snippet"]["publishedAt"],
            "description": item["snippet"]["description"],
            "playlists": ["Uploads"]
        }

    next_page_token = playlist_response.get("nextPageToken")
    if not next_page_token:
        break

# Step 3: Check other playlists for each video
for playlist_id, playlist_title in playlists.items():
    if playlist_id == uploads_playlist_id:
        continue
    next_page_token = None
    while True:
        items_request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        items_response = items_request.execute()
        for item in items_response["items"]:
            video_id = item["snippet"]["resourceId"]["videoId"]
            if video_id in video_data:
                video_data[video_id]["playlists"].append(playlist_title)
        next_page_token = items_response.get("nextPageToken")
        if not next_page_token:
            break

# Step 4: Fetch additional video metadata with videos.list
video_ids = list(video_data.keys())
for i in range(0, len(video_ids), 50):
    batch_ids = video_ids[i:i+50]
    video_request = youtube.videos().list(
        part="snippet,contentDetails,statistics",
        id=",".join(batch_ids)
    )
    video_response = video_request.execute()
    for item in video_response["items"]:
        video_id = item["id"]
        video_data[video_id].update({
            "duration": item["contentDetails"]["duration"],
            # Convert to int
            "view_count": int(item["statistics"].get("viewCount", "0")),
            # Convert to int
            "category_id": int(item["snippet"]["categoryId"]) if item["snippet"]["categoryId"] else 0
        })

# Step 5: Create and sort DataFrame
data = {
    "Video Title": [v["title"] for v in video_data.values()],
    "Video URL": [v["url"] for v in video_data.values()],
    "Playlists": [", ".join(v["playlists"]) for v in video_data.values()],
    "Day Posted": [v["published_at"] for v in video_data.values()],
    "Description": [v["description"] for v in video_data.values()],
    "Duration": [parse_duration(v.get("duration", "N/A")) for v in video_data.values()],
    "View Count": [v.get("view_count", 0) for v in video_data.values()],
    "Category ID": [v.get("category_id", 0) for v in video_data.values()]
}
df = pd.DataFrame(data)

# Convert "Day Posted" to timezone-unaware date only (YYYY-MM-DD)
df["Day Posted"] = pd.to_datetime(
    df["Day Posted"]).dt.tz_localize(None).dt.date

# Sort by "Day Posted" (latest first)
df = df.sort_values(by="Day Posted", ascending=False)
df.index = range(1, len(df) + 1)

# Step 6: Print and save to new files
print(f"Total videos found: {len(video_data)}")
print("\nFirst 5 rows of sorted DataFrame:")
print(df.head())

df.to_excel("seattle_data_guy_checklist2.xlsx", index=True, engine="openpyxl")
print("Checklist saved to 'seattle_data_guy_checklist2.xlsx'")

with open("seattle_data_guy_checklist2.txt", "w", encoding="utf-8") as f:
    for i, row in df.iterrows():
        f.write(
            f"{i}. [ ] {row['Video Title']} - {row['Video URL']} (Posted: {row['Day Posted']})\n")
print("Text checklist saved to 'seattle_data_guy_checklist2.txt'")
