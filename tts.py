from flask import Flask, request, jsonify
from AppKit import NSSpeechSynthesizer
import threading

app = Flask(__name__)

# Initialize the Apple TTS engine
synthesizer = NSSpeechSynthesizer.alloc().init()
fixed_voice = "com.apple.speech.synthesis.voice.samantha"
synthesizer.setVoice_(fixed_voice)

# Lock for thread safety since NSSpeechSynthesizer is not thread-safe
lock = threading.Lock()

@app.route('/speak', methods=['POST'])
def speak():
    """Endpoint to speak the provided text."""
    data = request.get_json()
    text = data.get('text', '')

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        with lock:
            synthesizer.startSpeakingString_(text)

            # Wait until the speech finishes
            while synthesizer.isSpeaking():
                pass
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Speech completed successfully."})

@app.route('/status', methods=['GET'])
def tts_status():
    """Endpoint to check if TTS is currently speaking."""
    return jsonify({"isSpeaking": synthesizer.isSpeaking()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=58851)
