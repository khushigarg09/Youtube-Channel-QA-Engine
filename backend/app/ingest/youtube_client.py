import re
from googleapiclient.discovery import build
from app.config import settings

class YouTubeClient:
    def __init__(self):
        self.api_key = settings.YOUTUBE_API_KEY
        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY not found in configuration.")
        self.youtube = build("youtube", "v3", developerKey=self.api_key)

    def extract_channel_info_from_url(self, url: str) -> dict:
        """
        Parses the URL and returns channel details from YouTube.
        Handles handles (@name), channel IDs (UC...), custom URLs, etc.
        """
        url = url.strip()
        
        # 1. Match Channel ID (e.g., /channel/UC...)
        channel_id_match = re.search(r"channel/(UC[a-zA-Z0-9_-]{22})", url)
        if channel_id_match:
            return self.get_channel_details(channel_id=channel_id_match.group(1))

        # 2. Match Custom Handle (e.g., /@username or custom name)
        handle_match = re.search(r"/(@[a-zA-Z0-9._-]+)", url)
        if handle_match:
            return self.get_channel_details(handle=handle_match.group(1))

        # 3. Match legacy usernames (e.g., /user/username)
        user_match = re.search(r"user/([a-zA-Z0-9_-]+)", url)
        if user_match:
            return self.get_channel_details(username=user_match.group(1))

        # 4. Fallback: try parsing the very last segment if it is a handle
        last_segment = url.split("/")[-1]
        if last_segment.startswith("@"):
            return self.get_channel_details(handle=last_segment)

        # 5. Search fallback: search for the channel name if it's just text
        return self.search_channel(url)

    def get_channel_details(self, channel_id: str = None, handle: str = None, username: str = None) -> dict:
        """
        Fetches channel details (ID, name, custom_url, thumbnail, uploads playlist ID).
        """
        params = {"part": "snippet,contentDetails"}
        if channel_id:
            params["id"] = channel_id
        elif handle:
            params["forHandle"] = handle
        elif username:
            params["forUsername"] = username
        else:
            raise ValueError("At least one parameter (channel_id, handle, or username) must be provided.")

        response = self.youtube.channels().list(**params).execute()
        items = response.get("items", [])
        if not items:
            # Fallback for handle queries if API is older or handle is structured differently
            if handle:
                # Try search
                return self.search_channel(handle)
            raise ValueError(f"Channel not found for parameters: {params}")

        channel = items[0]
        snippet = channel.get("snippet", {})
        content_details = channel.get("contentDetails", {})
        uploads_playlist_id = content_details.get("relatedPlaylists", {}).get("uploads")

        return {
            "channel_id": channel.get("id"),
            "channel_name": snippet.get("title"),
            "custom_url": snippet.get("customUrl"),
            "thumbnail_url": snippet.get("thumbnails", {}).get("default", {}).get("url"),
            "uploads_playlist_id": uploads_playlist_id
        }

    def search_channel(self, query: str) -> dict:
        """
        Searches for a channel matching a query term.
        """
        response = self.youtube.search().list(
            part="snippet",
            q=query,
            type="channel",
            maxResults=1
        ).execute()
        items = response.get("items", [])
        if not items:
            raise ValueError(f"No channel found for query: {query}")
        
        channel_id = items[0].get("id", {}).get("channelId")
        return self.get_channel_details(channel_id=channel_id)

    def get_all_videos_in_playlist(self, playlist_id: str) -> list:
        """
        Fetches all video metadata from the channel's uploads playlist.
        """
        videos = []
        next_page_token = None

        while True:
            response = self.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            items = response.get("items", [])
            for item in items:
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                
                # Fetch video details
                video_id = content_details.get("videoId")
                title = snippet.get("title")
                description = snippet.get("description")
                upload_date = snippet.get("publishedAt")
                
                # Get best available thumbnail
                thumbnails = snippet.get("thumbnails", {})
                thumbnail_url = (
                    thumbnails.get("maxres", {}).get("url") or
                    thumbnails.get("high", {}).get("url") or
                    thumbnails.get("medium", {}).get("url") or
                    thumbnails.get("default", {}).get("url")
                )

                videos.append({
                    "video_id": video_id,
                    "title": title,
                    "description": description,
                    "upload_date": upload_date,
                    "thumbnail_url": thumbnail_url,
                    "duration_seconds": 0  # Updated in a batch video query
                })

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        # Batch query durations to save quota. Videos list can take up to 50 IDs at a time.
        self.update_video_durations(videos)
        return videos

    def update_video_durations(self, videos: list):
        """
        Queries the video details API in batches of 50 to get duration_seconds.
        """
        video_ids = [v["video_id"] for v in videos]
        id_batches = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]

        duration_map = {}
        for batch in id_batches:
            response = self.youtube.videos().list(
                part="contentDetails",
                id=",".join(batch)
            ).execute()

            for item in response.get("items", []):
                v_id = item.get("id")
                iso_duration = item.get("contentDetails", {}).get("duration", "PT0S")
                duration_map[v_id] = self.parse_iso_duration(iso_duration)

        for video in videos:
            video["duration_seconds"] = duration_map.get(video["video_id"], 0)

    @staticmethod
    def parse_iso_duration(duration_str: str) -> int:
        """
        Parses ISO 8601 duration (e.g. PT1H2M10S) to seconds.
        """
        pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
        match = pattern.match(duration_str)
        if not match:
            return 0
        
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        
        return hours * 3600 + minutes * 60 + seconds
