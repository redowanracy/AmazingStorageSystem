import google.generativeai as genai
import logging
from typing import Dict, List, Optional, Tuple

from ..config import app_config
from ..core.file_processor import FileProcessor

logger = logging.getLogger(__name__)

class ChatbotClient:
    """Client to interact with the configured chatbot LLM."""

    def __init__(self):
        self.api_key = app_config.chatbot_api_key
        self.provider = app_config.chatbot_provider
        self.client = None
        self.model = None
        self.file_processor = None  # Will be set externally
        self.conversation_contexts: Dict[str, Dict[str, str]] = {}  # user_id -> {file_id -> content}

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

    def set_file_processor(self, file_processor: FileProcessor):
        """Set the file processor for extracting content from files."""
        self.file_processor = file_processor

    def is_enabled(self) -> bool:
        """Check if the chatbot client was initialized successfully."""
        return self.client is not None and self.model is not None

    def add_file_to_context(self, user_id: str, file_id: str) -> Tuple[bool, str]:
        """Add a file to the user's conversation context.
        
        Args:
            user_id: Unique identifier for the user
            file_id: ID of the file to add to context
            
        Returns:
            Tuple of (success, message)
        """
        if not self.file_processor:
            return False, "File processor not initialized."
        
        try:
            # Initialize user context if not exists
            if user_id not in self.conversation_contexts:
                self.conversation_contexts[user_id] = {}
            
            # Get file content
            filename, content = self.file_processor.get_file_content(file_id)
            
            # Add to user's context
            self.conversation_contexts[user_id][file_id] = {
                'filename': filename,
                'content': content
            }
            
            return True, f"Added file '{filename}' to conversation context."
        
        except Exception as e:
            logger.error(f"Error adding file {file_id} to context for user {user_id}: {e}", exc_info=True)
            return False, f"Error adding file to context: {str(e)}"

    def remove_file_from_context(self, user_id: str, file_id: str) -> bool:
        """Remove a file from the user's conversation context."""
        if user_id in self.conversation_contexts and file_id in self.conversation_contexts[user_id]:
            del self.conversation_contexts[user_id][file_id]
            return True
        return False

    def get_response(self, prompt: str, user_id: Optional[str] = None) -> str:
        """Gets a response from the configured LLM (synchronous).
        
        Args:
            prompt: The user's question or prompt
            user_id: Optional user ID to include file context
        """
        if not self.is_enabled():
            return "Sorry, the chatbot is not configured or enabled."

        # Build context-enhanced prompt if user_id is provided
        enhanced_prompt = prompt
        if user_id and user_id in self.conversation_contexts and self.conversation_contexts[user_id]:
            context_text = "\n\nReference Documents:\n"
            for file_id, file_data in self.conversation_contexts[user_id].items():
                context_text += f"\n--- Document: {file_data['filename']} ---\n"
                # Truncate content if too long (Gemini has context limits)
                content = file_data['content']
                if len(content) > 10000:  # Arbitrary limit, adjust based on model
                    content = content[:10000] + "... [content truncated]"
                context_text += content + "\n"
            
            # Create system context with file information
            system_context = (
                "You are an AI assistant that helps users understand their documents. "
                "Below are the contents of documents the user has uploaded. "
                "Use this information to answer the user's questions about these documents. "
                "If the question is not related to the documents, you can answer based on your general knowledge."
            )
            
            enhanced_prompt = f"{system_context}\n{context_text}\n\nUser Question: {prompt}"
            
        logger.info(f"Sending prompt to {self.provider}: '{enhanced_prompt[:50]}...'")
        
        try:
            if self.provider.lower() == 'gemini':
                response = self.model.generate_content(enhanced_prompt)
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
            raise RuntimeError(f"Sorry, an error occurred while contacting the chatbot: {e}")

async def main_test():
    print("Testing ChatbotClient...")
    client = ChatbotClient()
    if client.is_enabled():
        test_prompt = "Explain what this Amazing Storage System does in one sentence."
        print(f"Sending prompt: {test_prompt}")
        response = client.get_response(test_prompt)
        print(f"Received response: {response}")
    else:
        print("Chatbot is not enabled.")

if __name__ == '__main__':
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_test())