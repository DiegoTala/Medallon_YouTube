from medallon_youtube.mapping import flatten_comment_thread, flatten_video

RAW_VIDEO = {
    "id": "dQw4w9WgXcQ",
    "snippet": {
        "title": "Awesome Mix",
        "description": "A test video",
        "channelTitle": "DJ Test",
        "publishedAt": "2026-07-01T12:00:00Z",
        "defaultLanguage": "en",
    },
    "contentDetails": {"duration": "PT3M30S"},
    "statistics": {"viewCount": "1000", "likeCount": "50"},
}


def test_flatten_video_maps_all_fields() -> None:
    flat = flatten_video(RAW_VIDEO)

    assert flat == {
        "video_id": "dQw4w9WgXcQ",
        "channel_name": "DJ Test",
        "title": "Awesome Mix",
        "description": "A test video",
        "published_at": "2026-07-01T12:00:00Z",
        "default_language": "en",
        "duration": "PT3M30S",
        "view_count": 1000,
        "like_count": 50,
    }


def test_flatten_video_defaults_missing_stats_to_zero() -> None:
    raw = {"id": "v1", "snippet": {}, "contentDetails": {}, "statistics": {}}
    flat = flatten_video(raw)
    assert flat["view_count"] == 0
    assert flat["like_count"] == 0


THREAD_WITH_REPLY = {
    "video_id": "dQw4w9WgXcQ",
    "thread": {
        "snippet": {
            "topLevelComment": {
                "id": "Ugyy1abc2def3ghi",
                "snippet": {
                    "authorDisplayName": "TestUser",
                    "textOriginal": "Great video!",
                    "likeCount": 5,
                    "publishedAt": "2026-07-01T12:30:00Z",
                },
            }
        },
        "replies": {
            "comments": [
                {
                    "id": "Ugyy1abc2def3ghi.reply1",
                    "snippet": {
                        "authorDisplayName": "ReplyUser",
                        "textOriginal": "Totally agree!",
                        "likeCount": 1,
                        "publishedAt": "2026-07-01T13:00:00Z",
                    },
                }
            ]
        },
    },
}


def test_flatten_comment_thread_expands_top_level_and_replies() -> None:
    flat = flatten_comment_thread(THREAD_WITH_REPLY)

    assert len(flat) == 2
    assert flat[0]["comment_id"] == "Ugyy1abc2def3ghi"
    assert flat[0]["video_id"] == "dQw4w9WgXcQ"
    assert flat[0]["author"] == "TestUser"
    assert flat[1]["comment_id"] == "Ugyy1abc2def3ghi.reply1"
    assert flat[1]["video_id"] == "dQw4w9WgXcQ"
    assert flat[1]["author"] == "ReplyUser"


def test_flatten_comment_thread_no_replies() -> None:
    bronze_line = {
        "video_id": "v1",
        "thread": {
            "snippet": {
                "topLevelComment": {
                    "id": "c1",
                    "snippet": {
                        "authorDisplayName": "A",
                        "textOriginal": "hi",
                        "likeCount": 0,
                        "publishedAt": "2026-07-01T12:00:00Z",
                    },
                }
            }
        },
    }

    flat = flatten_comment_thread(bronze_line)

    assert len(flat) == 1
    assert flat[0]["comment_id"] == "c1"
