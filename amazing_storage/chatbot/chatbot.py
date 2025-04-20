import google.generativeai as genai
import logging

from ..config import app_config

logger = logging.getLogger(__name__)

class ChatbotClient:
    """Client to interact with the configured chatbot LLM."""

    def __init__(self):
        self.api_key = app_config.chatbot_api_key
        self.provider = app_config.chatbot_provider
        self.client = None
        self.model = None

        if not self.api_key:
            logger.warning("Chatbot API key not configured. Chatbot disabled.")
            return
        
        if self.provider and self.provider.lower() == 'gemini':
            try:
                genai.configure(api_key=self.api_key)
                
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                self.client = genai
                logger.info(f"Gemini chatbot client initialized with model: {self.model.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}", exc_info=True)
                self.client = None
                self.model = None
        else:
            logger.warning(f"Chatbot provider '{self.provider}' not recognized or configured. Chatbot disabled.")

    def is_enabled(self) -> bool:
        """Check if the chatbot client was initialized successfully."""
        return self.client is not None and self.model is not None

    async def get_response(self, prompt: str) -> str:
        """Gets a response from the configured LLM."""
        if not self.is_enabled():
            return "Sorry, the chatbot is not configured or enabled."

        logger.info(f"Sending prompt to {self.provider}: '{prompt[:50]}...'")
        
        try:
            if self.provider.lower() == 'gemini':
                response = await self.model.generate_content_async(prompt)
                if not response.parts:
                     logger.warning("Gemini response has no parts (potentially blocked).")
                     if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                          logger.warning(f"Prompt Feedback: {response.prompt_feedback}")
                     return "Sorry, I couldn't generate a response for that (it might have been blocked)."
                return response.text
            
            else:
                return f"Chatbot provider '{self.provider}' logic not implemented."

        except Exception as e:
            logger.error(f"Error getting response from {self.provider}: {e}", exc_info=True)
            return f"Sorry, an error occurred while contacting the chatbot: {e}"

async def main_test():
    print("Testing ChatbotClient...")
    client = ChatbotClient()
    if client.is_enabled():
        test_prompt = "Explain what this Amazing Storage System does in one sentence."
        print(f"Sending prompt: {test_prompt}")
        response = await client.get_response(test_prompt)
        print(f"Received response: {response}")
    else:
        print("Chatbot is not enabled.")

if __name__ == '__main__':
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_test()) 