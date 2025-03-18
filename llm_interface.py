import requests
import traceback

class LLMInterface:
    def __init__(self, model_name="llama-3.2-3b-instruct", lm_studio_url="http://localhost:1234/v1/chat/completions"):
        self.model_name = model_name
        self.lm_studio_url = lm_studio_url
        self.transcript = []

    def set_transcript(self, transcript):
        """Set the conversation transcript."""
        self.transcript = transcript

    def get_transcript(self):
        """Get the current conversation transcript."""
        return self.transcript

    def query_llm(self, prompt, temperature=0.7, max_tokens=200, is_event_update=False):
        """
        Queries the language model.

        Args:
            prompt (str): The user prompt to send to the LLM
            temperature (float): The sampling temperature
            max_tokens (int): Maximum number of tokens to generate
            is_event_update (bool): If True, increases token limit for event processing

        Returns:
            str: The LLM response or an error message
        """
        try:
            # Add user message to transcript
            self.transcript.append({"role": "user", "content": prompt})

            # Adjust token limit for event processing if needed
            if is_event_update:
                max_tokens = 300

            # Prepare the payload
            lm_payload = {
                "model": self.model_name,
                "messages": self.transcript,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }

            # Send request to LM Studio
            response = requests.post(self.lm_studio_url, json=lm_payload)
            response.raise_for_status()

            # Extract response
            lm_reply = response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            if not lm_reply:
                print("Warning: Empty response from LLM")
                return "Sorry, I didn't understand that. Can you rephrase?"

            # Add assistant message to transcript
            self.transcript.append({"role": "assistant", "content": lm_reply})
            return lm_reply

        except requests.exceptions.RequestException as e:
            print(f"Error communicating with LM Studio server: {e}")
            return "I'm having trouble reaching my knowledge base. Try again later."
        except Exception as e:
            print(f"Unexpected error in query_llm: {e}")
            traceback.print_exc()
            return "I encountered an unexpected error. Please try again."