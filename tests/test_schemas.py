from medallon_youtube.schemas import YouTubeCommentSchema, YouTubeVideoSchema


def test_video_schema_valid() -> None:
    data = {
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
    video = YouTubeVideoSchema(**data)
    assert video.video_id == "dQw4w9WgXcQ"


def test_video_schema_blank_title_raises() -> None:
    data = {
        "video_id": "dQw4w9WgXcQ",
        "channel_name": "DJ Test",
        "title": "   ",
        "description": "A test video",
        "published_at": "2026-07-01T12:00:00Z",
        "default_language": "en",
        "duration": "PT3M30S",
        "view_count": 1000,
        "like_count": 50,
    }
    try:
        YouTubeVideoSchema(**data)
        assert False, "Expected ValidationError"
    except Exception:
        pass


def test_comment_schema_valid() -> None:
    data = {
        "comment_id": "Ugyy1abc2def3ghi",
        "video_id": "dQw4w9WgXcQ",
        "author": "TestUser",
        "comment_text": "Great video!",
        "like_count": 5,
        "published_at": "2026-07-01T12:30:00Z",
    }
    comment = YouTubeCommentSchema(**data)
    assert comment.author == "TestUser"


def test_comment_schema_blank_text_raises() -> None:
    data = {
        "comment_id": "Ugyy1abc2def3ghi",
        "video_id": "dQw4w9WgXcQ",
        "author": "TestUser",
        "comment_text": "   ",
        "like_count": 5,
        "published_at": "2026-07-01T12:30:00Z",
    }
    try:
        YouTubeCommentSchema(**data)
        assert False, "Expected ValidationError"
    except Exception:
        pass
