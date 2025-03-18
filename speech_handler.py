import os
import requests
import azure.cognitiveservices.speech as speechsdk
from datetime import datetime

class SpeechHandler:
    def __init__(self, speech_key, speech_region, tts_url="http://localhost:58851/speak"):
        self.speech_key = speech_key
        self.speech_region = speech_region
        self.tts_url = tts_url
        self.speech_recognizer = None
        self.last_tts_response = None
        self.callback_function = None
        self.session_active = True

    def set_callback(self, callback_function):
        """Set the callback function that will process recognized speech."""
        self.callback_function = callback_function

    def send_to_tts(self, text):
        """Sends text to the TTS service for speech synthesis."""
        tts_payload = {"text": text}
        try:
            tts_response = requests.post(self.tts_url, json=tts_payload)
            tts_response.raise_for_status()
            self.last_tts_response = text
            return True
        except Exception as e:
            print(f"Error communicating with TTS service: {e}")
            return False

    def pause_transcription(self):
        """Pauses continuous speech recognition."""
        if self.speech_recognizer:
            self.speech_recognizer.stop_continuous_recognition_async()
            self.speech_recognizer = None

    def resume_transcription(self):
        """Resumes continuous speech recognition."""
        self.start_transcription()

    def start_transcription(self):
        """Starts continuous speech recognition."""
        if self.speech_recognizer:
            self.speech_recognizer.stop_continuous_recognition_async()
            self.speech_recognizer = None

        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.speech_region)
        speech_config.speech_recognition_language = 'en-GB'
        self.speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config)

        def recognized_callback(evt):
            user_input = evt.result.text.strip()
            print(f"\033[95mRecognised: {user_input}\033[0m")

            if "stop session" in user_input.lower():
                print("\033[93mSession stopped by user.\033[0m")
                self.session_active = False
                self.pause_transcription()
                return

            if not self.session_active:
                return
            self.pause_transcription()
            if self.callback_function:
                self.callback_function(user_input)
            self.resume_transcription()

        def cancelled_callback(evt):
            print(f"Speech Recognition cancelled: {evt.reason}")
            if evt.reason == speechsdk.CancellationReason.Error:
                print(f"Error Details: {evt.error_details}")

        self.speech_recognizer.recognized.connect(recognized_callback)
        self.speech_recognizer.canceled.connect(cancelled_callback)

        print("\033[93mSpeak into the microphone. Say 'stop session' to pause or stop.\033[0m")
        self.speech_recognizer.start_continuous_recognition_async()

    def get_last_response(self):
        """Returns the last TTS response."""
        return self.last_tts_response

    def is_session_active(self):
        """Returns whether the session is active."""
        return self.session_active

    def set_session_active(self, active):
        """Sets whether the session is active."""
        self.session_active = active