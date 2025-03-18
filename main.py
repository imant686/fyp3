from assistant import AI_Assistant

def main():
    ai_assistant = AI_Assistant()
    greeting = "Hello, my name is Samantha and I am your voice assistant. Say 'stop session' to stop the session. How may I help?"
    ai_assistant.send_to_tts(greeting)
    ai_assistant.start_transcription()
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Program interrupted. Stopping recognition.")
        ai_assistant.pause_transcription()

if __name__ == "__main__":
    main()