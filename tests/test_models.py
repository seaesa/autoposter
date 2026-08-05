def test_tiktok_channel_model_creation():
    from sqlmodel import SQLModel, Session, create_engine
    from app.models import TikTokChannel

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        channel = TikTokChannel(
            username="testuser",
            display_name="Test User",
            is_active=True
        )
        session.add(channel)
        session.commit()
        session.refresh(channel)

        assert channel.id is not None
        assert channel.username == "testuser"
        assert channel.display_name == "Test User"
        assert channel.is_active == True