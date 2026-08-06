from topic_picker import choose_topic


def main():
    topic = choose_topic()

    print("=" * 60)
    print("AI VIDEO PUBLISHER")
    print("=" * 60)

    print(f"Category : {topic['category']}")
    print(f"Topic    : {topic['topic']}")
    print(f"Duration : {topic['duration_minutes']} minutes")
    print(f"Language : {topic['language']}")

    print()
    print("Next stages:")
    print("1. Web research")
    print("2. AI script generation")
    print("3. Voice generation")
    print("4. Visual asset collection")
    print("5. FFmpeg rendering")
    print("6. Instagram publishing")
    print("7. TikTok publishing")


if __name__ == "__main__":
    main()
