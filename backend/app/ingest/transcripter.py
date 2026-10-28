import os
import logging
from pathlib import Path
import yt_dlp
from groq import Groq
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    RequestBlocked,
    IpBlocked,
    YouTubeRequestFailed,
)
from app.config import settings

logger = logging.getLogger(__name__)

TRANSCRIPT_FALLBACK_ERRORS = (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    RequestBlocked,
    IpBlocked,
    YouTubeRequestFailed,
)


def get_temp_audio_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "temp_audio"


class TranscriptsDisabledError(ValueError):
    pass

class NoTranscriptFoundError(ValueError):
    pass

class Transcripter:
    @staticmethod
    def get_transcript(video_id: str) -> list:
        """
        Fetches the transcript for a given YouTube video ID.
        Falls back to Groq Whisper transcription if standard subtitles are disabled or unavailable.
        Returns a list of dicts: [{'text': str, 'start': float, 'duration': float}]
        """
        try:
            # Instantiate the API client
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            
            # Find English transcript: Prefer manually uploaded first, then auto-generated
            try:
                transcript = transcript_list.find_manually_created_transcript(['en'])
                logger.info(f"Found manual English transcript for video {video_id}.")
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_generated_transcript(['en'])
                    logger.info(f"Found auto-generated English transcript for video {video_id}.")
                except NoTranscriptFound:
                    # If English isn't found, try to translate any available transcript to English
                    first_transcript = next(iter(transcript_list))
                    if first_transcript.is_translatable:
                        transcript = first_transcript.translate('en')
                        logger.info(f"Translated foreign transcript to English for video {video_id}.")
                    else:
                        transcript = first_transcript
                        logger.warning(f"No English or translatable transcripts found. Using raw transcript for video {video_id}.")
                
            snippets = transcript.fetch()
            return [
                {
                    "text": s.text,
                    "start": s.start,
                    "duration": s.duration
                }
                for s in snippets
            ]
        except TRANSCRIPT_FALLBACK_ERRORS as exc:
            logger.info(
                "Transcript unavailable for %s; attempting Whisper fallback: %s",
                video_id,
                exc,
            )
            return Transcripter.transcribe_with_whisper(video_id)

    @staticmethod
    def transcribe_with_whisper(video_id: str) -> list:
        """
        Downloads a lightweight M4A audio stream for the given video_id using yt-dlp,
        transcribes it via Groq's Whisper API (splitting the file if it exceeds 24MB),
        and returns transcript segment dictionary structures.
        Cleans up all temporary audio files in an outer try/finally block.
        """
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured. Whisper fallback cannot run.")

        temp_dir = get_temp_audio_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio_path = os.path.join(temp_dir, f"{video_id}.m4a")

        def cleanup_temp_files():
            """Ensures all temporary audio files for this video are removed."""
            if not os.path.exists(temp_dir):
                return
            try:
                for fname in os.listdir(temp_dir):
                    if fname.startswith(video_id):
                        target = os.path.join(temp_dir, fname)
                        if os.path.isfile(target):
                            try:
                                os.remove(target)
                                logger.info(f"Cleaned up temp audio file: {target}")
                            except Exception as rm_err:
                                logger.warning(f"Could not remove temp audio file {target}: {rm_err}")
            except Exception as list_err:
                logger.warning(f"Error scanning temp directory during cleanup: {list_err}")

        try:
            # 1. Download raw M4A audio stream (format 139) from YouTube
            ydl_opts = {
                "format": "139",  # 48kbps M4A audio stream directly (~20MB/hour)
                "outtmpl": os.path.join(temp_dir, f"{video_id}.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
            }

            logger.info(f"Downloading M4A audio stream for video {video_id} using yt-dlp...")
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"https://youtube.com/watch?v={video_id}"])
            except Exception as e:
                logger.warning(f"Format 139 download failed for video {video_id}, retrying with worst audio format fallback: {e}")
                ydl_opts["format"] = "worstaudio/worst"
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([f"https://youtube.com/watch?v={video_id}"])
                except Exception as retry_err:
                    raise ValueError(f"Failed to download audio for video {video_id}: {str(retry_err)}")

            if not os.path.exists(audio_path):
                found_files = [f for f in os.listdir(temp_dir) if f.startswith(video_id)]
                if found_files:
                    audio_path = os.path.join(temp_dir, found_files[0])
                else:
                    raise FileNotFoundError(f"Audio file for video {video_id} was not generated by yt-dlp.")

            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            
            # 2. Audio Slicing (if size exceeds 24MB to fit Groq API limits)
            if file_size_mb > 24.0:
                logger.info(f"Audio file size ({file_size_mb:.2f} MB) exceeds Groq's 25MB limit. Splitting into chunks...")
                try:
                    from pydub import AudioSegment
                    
                    chunk_duration_ms = 20 * 60 * 1000
                    audio_segment = AudioSegment.from_file(audio_path)
                    duration_ms = len(audio_segment)
                    
                    sliced_segments = []
                    base_name = os.path.splitext(os.path.basename(audio_path))[0]
                    
                    for i, start_ms in enumerate(range(0, duration_ms, chunk_duration_ms)):
                        end_ms = min(start_ms + chunk_duration_ms, duration_ms)
                        part = audio_segment[start_ms:end_ms]
                        
                        part_name = f"{base_name}_part{i}.m4a"
                        part_path = os.path.join(temp_dir, part_name)
                        
                        part.export(part_path, format="ipod")
                        sliced_segments.append({
                            "path": part_path,
                            "offset": start_ms / 1000.0
                        })
                    
                    logger.info(f"Successfully sliced audio into {len(sliced_segments)} parts.")
                    
                    all_segments = []
                    client = Groq(api_key=settings.GROQ_API_KEY)
                    
                    for idx, seg in enumerate(sliced_segments):
                        part_path = seg["path"]
                        offset = seg["offset"]
                        
                        logger.info(f"Transcribing segment {idx+1}/{len(sliced_segments)}: {os.path.basename(part_path)} (offset: {offset:.1f}s)...")
                        with open(part_path, "rb") as file:
                            response = client.audio.transcriptions.create(
                                file=(os.path.basename(part_path), file.read()),
                                model="whisper-large-v3",
                                response_format="verbose_json"
                            )
                        
                        raw_segs = getattr(response, "segments", [])
                        if isinstance(raw_segs, list):
                            for rseg in raw_segs:
                                if isinstance(rseg, dict):
                                    start = float(rseg.get("start", 0.0)) + offset
                                    end = float(rseg.get("end", 0.0)) + offset
                                    text = rseg.get("text", "").strip()
                                else:
                                    start = float(getattr(rseg, "start", 0.0)) + offset
                                    end = float(getattr(rseg, "end", 0.0)) + offset
                                    text = getattr(rseg, "text", "").strip()
                                
                                all_segments.append({
                                    "text": text,
                                    "start": start,
                                    "duration": max(end - start, 0.0)
                                })
                    
                    logger.info(f"Whisper sliced transcription completed. Stitching finished: {len(all_segments)} segments total.")
                    return all_segments
                    
                except Exception as split_err:
                    logger.warning(
                        f"Audio splitting failed: {split_err}. "
                        "Attempting full audio file transcription directly..."
                    )

            # 3. Standard full-file transcription
            logger.info(f"Sending audio file {os.path.basename(audio_path)} ({os.path.getsize(audio_path) / (1024*1024):.2f} MB) to Groq Whisper API...")
            client = Groq(api_key=settings.GROQ_API_KEY)
            with open(audio_path, "rb") as file:
                response = client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json"
                )
            
            segments = []
            raw_segments = getattr(response, "segments", [])
            if isinstance(raw_segments, list):
                for seg in raw_segments:
                    if isinstance(seg, dict):
                        start = float(seg.get("start", 0.0))
                        end = float(seg.get("end", 0.0))
                        text = seg.get("text", "").strip()
                    else:
                        start = float(getattr(seg, "start", 0.0))
                        end = float(getattr(seg, "end", 0.0))
                        text = getattr(seg, "text", "").strip()
                    
                    segments.append({
                        "text": text,
                        "start": start,
                        "duration": max(end - start, 0.0)
                    })
            
            logger.info(f"Whisper transcription succeeded. Extracted {len(segments)} segments.")
            return segments

        except Exception as api_err:
            raise ValueError(f"Groq Whisper transcription failed for video {video_id}: {str(api_err)}")
        finally:
            cleanup_temp_files()

    @staticmethod
    def chunk_transcript(transcript: list, target_chunk_size: int = 800, overlap_chars: int = 150) -> list:
        """
        Groups transcript segments into larger chunks of ~target_chunk_size characters,
        preserving chronological timestamps and adding a sliding window overlap of ~overlap_chars.
        Each chunk: { 'text': str, 'start_time': float, 'duration': float }
        """
        if not transcript:
            return []

        chunks = []
        current_segments = []
        current_char_count = 0

        for segment in transcript:
            text = segment.get("text", "").strip()
            if not text:
                continue

            current_segments.append(segment)
            current_char_count += len(text) + 1  # Add 1 for space

            # When character count reaches target chunk size, close the chunk
            if current_char_count >= target_chunk_size:
                chunk_text = " ".join([s.get("text", "").strip() for s in current_segments if s.get("text", "").strip()])
                start_time = float(current_segments[0].get("start", 0.0))
                last_seg = current_segments[-1]
                end_time = float(last_seg.get("start", 0.0)) + float(last_seg.get("duration", 0.0))
                duration = max(end_time - start_time, 0.0)

                chunks.append({
                    "text": chunk_text,
                    "start_time": start_time,
                    "duration": duration
                })

                # Slide window: pop elements from the front of current_segments
                # until the remaining elements are under overlap_chars size
                while len(current_segments) > 1:
                    first_seg_len = len(current_segments[0].get("text", "").strip()) + 1
                    remaining_char_count = current_char_count - first_seg_len
                    
                    if remaining_char_count >= overlap_chars:
                        current_segments.pop(0)
                        current_char_count = remaining_char_count
                    else:
                        break

        # Handle trailing segments if any are left
        if current_segments:
            chunk_text = " ".join([s.get("text", "").strip() for s in current_segments if s.get("text", "").strip()])
            start_time = float(current_segments[0].get("start", 0.0))
            last_seg = current_segments[-1]
            end_time = float(last_seg.get("start", 0.0)) + float(last_seg.get("duration", 0.0))
            duration = max(end_time - start_time, 0.0)

            # Avoid adding duplicate trailing chunks if they were already fully covered
            is_duplicate = False
            if chunks and chunks[-1]["text"] == chunk_text:
                is_duplicate = True

            if not is_duplicate and chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "start_time": start_time,
                    "duration": duration
                })

        return chunks
