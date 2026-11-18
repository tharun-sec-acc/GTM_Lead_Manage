import re
from typing import Any


def clean_speaker_name(name: str | None, default: str = "Participant") -> str:
    if not name or not name.strip():
        return default
    cleaned = name.strip()
    # Remove email or uuid brackets if present
    cleaned = re.sub(r"<[^>]+>", "", cleaned).strip()
    return cleaned or default


def normalize_transcript_entry(
    speaker_name: str | None,
    text: str | None,
    start_timestamp: str | None = None,
    end_timestamp: str | None = None,
    original_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a transcript utterance into a standard dictionary representation."""
    return {
        "speaker_name": clean_speaker_name(speaker_name),
        "text": (text or "").strip(),
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "original_metadata": original_metadata or {},
    }


def parse_vtt_content(vtt_text: str) -> list[dict[str, Any]]:
    """Parse WebVTT content (used by Microsoft Teams / Zoom transcripts)."""
    lines = vtt_text.splitlines()
    entries = []
    current_time_match = None
    current_speaker = "Speaker"
    current_text_lines = []

    time_re = re.compile(
        r"((?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}\.\d{3})"
    )

    for line in lines:
        line_str = line.strip()
        if not line_str or line_str.startswith("WEBVTT") or line_str.startswith("NOTE"):
            continue

        match = time_re.search(line_str)
        if match:
            if current_time_match and current_text_lines:
                entries.append(
                    normalize_transcript_entry(
                        speaker_name=current_speaker,
                        text=" ".join(current_text_lines),
                        start_timestamp=current_time_match.group(1),
                        end_timestamp=current_time_match.group(2),
                    )
                )
                current_text_lines = []
            current_time_match = match
            continue

        if current_time_match:
            # Check if line has <v SpeakerName> or SpeakerName: text
            if line_str.startswith("<v ") and ">" in line_str:
                speaker_end = line_str.find(">")
                current_speaker = line_str[3:speaker_end]
                text_part = line_str[speaker_end + 1 :].replace("</v>", "").strip()
                if text_part:
                    current_text_lines.append(text_part)
            elif ":" in line_str and not line_str.startswith("http"):
                parts = line_str.split(":", 1)
                current_speaker = parts[0].strip()
                current_text_lines.append(parts[1].strip())
            else:
                current_text_lines.append(line_str)

    if current_time_match and current_text_lines:
        entries.append(
            normalize_transcript_entry(
                speaker_name=current_speaker,
                text=" ".join(current_text_lines),
                start_timestamp=current_time_match.group(1),
                end_timestamp=current_time_match.group(2),
            )
        )

    return entries
