import logging
import os
import tempfile
import asyncio
import traceback
from typing import List, Tuple

from telegram import Update, BotCommand, InputFile
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Relative imports from parent directories
from ..config import app_config
from ..core.metadata import MetadataManager
from ..core.chunk_manager import ChunkManager
from ..chatbot.chatbot import ChatbotClient # Import chatbot client

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# --- Global instances (consider dependency injection for larger apps) ---
# Initialize core components needed by the bot
# Use a separate metadata dir or ensure thread-safety if sharing with web app
# For now, assume separate or sequential execution
metadata_manager_bot = MetadataManager(metadata_dir="metadata") 
chunk_manager_bot = ChunkManager(metadata_manager_bot)
chatbot_client = ChatbotClient() # Instantiate the chatbot client

# --- Bot Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I'm the Amazing Storage Bot. "
        rf"Send me a file to upload it, or use /help to see commands.",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a help message listing commands when /help is issued."""
    help_text = (
        "Available commands:\n"
        "/list - List all stored files\n"
        "/download <file_id> - Download a file by its ID\n"
        "/delete <file_id> - Delete a file by its ID\n"
        "\nSend any document/file to upload it."
    )
    await update.message.reply_text(help_text)

async def list_files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists stored files."""
    logger.info(f"User {update.effective_user.id} requested file list.")
    try:
        files: List[Tuple[str, str]] = chunk_manager_bot.list_files()
        if not files:
            await update.message.reply_text("No files stored yet.")
            return

        message = "Stored files:\n\n"
        # Sort by filename for display
        files.sort(key=lambda item: item[1].lower()) 
        
        # Function to escape HTML characters
        def escape_html(text: str) -> str:
            return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
        for file_id, filename in files:
            safe_filename = escape_html(filename)
            safe_file_id = escape_html(file_id) 
            # Use HTML tags like <code> for monospace
            message += f"- <code>{safe_filename}</code>\n  ID: <code>{safe_file_id}</code>\n"
            
        # Consider pagination for large file lists
        if len(message) > 4096: # Telegram message length limit
             message = message[:4000] + "\n... (list truncated)"
             
        # Use reply_html instead of reply_markdown_v2
        await update.message.reply_html(message)

    except Exception as e:
        logger.error(f"Error listing files for user {update.effective_user.id}: {e}", exc_info=True)
        await update.message.reply_text(f"Sorry, an error occurred while listing files: {e}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles receiving a document (file upload)."""
    if not update.message or not update.message.document:
        logger.warning("Received non-document message in document handler.")
        return

    user_id = update.effective_user.id
    doc = update.message.document
    original_filename = doc.file_name
    file_size = doc.file_size # Approximate size
    
    logger.info(f"User {user_id} is uploading '{original_filename}' (Size: ~{file_size / (1024*1024):.2f} MB)")
    await update.message.reply_text(f"Received '{original_filename}'. Starting upload process...")

    # Download the file from Telegram to a temporary location
    temp_dir = tempfile.mkdtemp(prefix='ass_bot_upload_')
    temp_path = os.path.join(temp_dir, original_filename) # Use original name for temp file
    file_id_telegram = doc.file_id
    
    try:
        bot = context.bot
        file_telegram = await bot.get_file(file_id_telegram)
        logger.info(f"Downloading Telegram file {file_id_telegram} to {temp_path}")
        await file_telegram.download_to_drive(temp_path)
        logger.info(f"Downloaded successfully.")

        # Upload using ChunkManager
        logger.info(f"Starting chunked upload for {temp_path}")
        uploaded_file_id = chunk_manager_bot.upload_file(temp_path, original_filename=original_filename)

        if uploaded_file_id:
            logger.info(f"Successfully uploaded '{original_filename}' for user {user_id}. File ID: {uploaded_file_id}")
            await update.message.reply_text(
                f"Successfully uploaded '{original_filename}'\nFile ID: `{uploaded_file_id}`",
                 parse_mode='MarkdownV2'
            )
        else:
            logger.error(f"Chunked upload failed for '{original_filename}' from user {user_id}.")
            await update.message.reply_text(f"Sorry, the upload of '{original_filename}' failed. Please check the logs or try again.")

    except Exception as e:
        logger.error(f"Error processing upload for '{original_filename}' from user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred during upload: {e}")
    finally:
        # Clean up temporary directory and file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_dir):
                 os.rmdir(temp_dir) # Only removes if empty
            logger.info(f"Cleaned up temporary upload resources for '{original_filename}'.")
        except OSError as cleanup_error:
            logger.error(f"Error cleaning up temp file/dir {temp_path}: {cleanup_error}")
            

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /download command."""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Please provide the File ID to download. Usage: /download <file_id>")
        return

    file_id_to_download = context.args[0]
    logger.info(f"User {user_id} requested download for file ID: {file_id_to_download}")

    manifest = metadata_manager_bot.load_manifest(file_id_to_download)
    if not manifest:
        await update.message.reply_text(f"Error: File ID '{file_id_to_download}' not found.")
        return

    await update.message.reply_text(f"Starting download for '{manifest.original_filename}'...")

    temp_dir = tempfile.mkdtemp(prefix='ass_bot_download_')
    # Secure filename just in case, though manifest should be trusted source
    from werkzeug.utils import secure_filename 
    safe_filename = secure_filename(manifest.original_filename)
    download_path = os.path.join(temp_dir, safe_filename)

    try:
        logger.info(f"Downloading file {file_id_to_download} to temp path {download_path}")
        chunk_manager_bot.download_file(file_id_to_download, download_path)
        logger.info(f"File reassembled locally at {download_path}")
        
        # Check file size before sending (Telegram has limits, often 50MB for bots)
        file_size = os.path.getsize(download_path)
        if file_size > 50 * 1024 * 1024: # Example 50MB limit
             logger.warning(f"File {download_path} ({file_size} bytes) exceeds Telegram bot limit.")
             await update.message.reply_text(f"Sorry, '{manifest.original_filename}' is too large ({file_size / (1024*1024):.1f}MB) to send back via Telegram.")
             return
             
        # Send the document with potentially increased timeouts
        await update.message.reply_text("Reassembly complete. Sending file back to you now...")
        with open(download_path, 'rb') as doc_file:
            await update.message.reply_document(
                document=doc_file, 
                filename=manifest.original_filename,
                read_timeout=60, # Increase read timeout (default is 20)
                write_timeout=60 # Increase write timeout (default is 20)
            )
        logger.info(f"Successfully sent file {file_id_to_download} to user {user_id}.")
        
    except FileNotFoundError as e:
        logger.error(f"Download failed for user {user_id}, file ID {file_id_to_download}: {e}", exc_info=True)
        await update.message.reply_text(f"Download failed: A required chunk might be missing or the manifest is invalid.")
    except Exception as e:
        logger.error(f"Error processing download for {file_id_to_download} from user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred during download: {e}")
    finally:
        # Clean up temporary directory and file
        try:
            if os.path.exists(download_path):
                os.remove(download_path)
            if os.path.exists(temp_dir):
                # Use shutil.rmtree for potentially non-empty dirs if needed, be careful!
                # shutil.rmtree(temp_dir, ignore_errors=True)
                os.rmdir(temp_dir) 
            logger.info(f"Cleaned up temporary download resources for '{file_id_to_download}'.")
        except OSError as cleanup_error:
             logger.error(f"Error cleaning up temp file/dir {download_path}: {cleanup_error}")

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /delete command."""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Please provide the File ID to delete. Usage: /delete <file_id>")
        return

    file_id_to_delete = context.args[0]
    logger.info(f"User {user_id} requested deletion for file ID: {file_id_to_delete}")
    
    # Optional: Add a confirmation step here?
    
    manifest = metadata_manager_bot.load_manifest(file_id_to_delete) # Check if exists first
    original_name = manifest.original_filename if manifest else "(unknown name)"

    try:
        success = chunk_manager_bot.delete_file(file_id_to_delete)
        if success:
            logger.info(f"Successfully deleted file ID {file_id_to_delete} for user {user_id}.")
            await update.message.reply_text(f"Successfully deleted file '{original_name}' (ID: {file_id_to_delete}).")
        else:
            # This might happen if manifest was found but chunk deletion failed partially
            logger.warning(f"Deletion process for file ID {file_id_to_delete} reported issues (user {user_id}).")
            await update.message.reply_text(f"Deletion process for '{original_name}' completed, but there might have been issues deleting some parts. The manifest file should be gone.")
            
    except Exception as e:
        logger.error(f"Error processing deletion for {file_id_to_delete} from user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred during deletion: {e}")

# --- Text Message Handler (for Chatbot) ---

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles regular text messages by sending them to the chatbot."""
    if not update.message or not update.message.text:
        return # Should not happen with the filter used

    user_id = update.effective_user.id
    prompt = update.message.text
    logger.info(f"User {user_id} sent text message: '{prompt[:50]}...'")

    if not chatbot_client.is_enabled():
        # Optional: Reply only once or less frequently if chatbot is disabled
        # if not context.user_data.get('chatbot_disabled_notified', False):
        #     await update.message.reply_text("The chatbot feature is currently disabled.")
        #     context.user_data['chatbot_disabled_notified'] = True
        logger.warning("Chatbot is disabled, ignoring text message.")
        return

    # Indicate thinking...
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    response_text = await chatbot_client.get_response(prompt)
    
    # Send the chatbot's response back
    await update.message.reply_text(response_text)


# --- Bot Setup ---

async def post_init(application: Application):
    """Sets the bot commands list after initialization."""
    commands = [
        BotCommand("start", "Start interacting with the bot"),
        BotCommand("help", "Show available commands"),
        BotCommand("list", "List stored files"),
        BotCommand("download", "Download a file by ID (e.g., /download <file_id>)"),
        BotCommand("delete", "Delete a file by ID (e.g., /delete <file_id>)"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set.")

    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document)) # Handle any document
    
    # Add the text message handler - Filters.TEXT & ~filters.COMMAND ensures it only catches non-command text
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Consider adding handlers for photos, videos, etc. if needed
    # application.add_handler(MessageHandler(filters.PHOTO, handle_photo))


def run_bot():
    """Runs the Telegram bot."""
    bot_token = app_config.telegram_bot_token
    if not bot_token:
        logger.error("Telegram bot token (ASS_TELEGRAM_BOT_TOKEN) not found. Bot cannot start.")
        print("Error: Telegram bot token not configured.")
        return

    logger.info("Starting Telegram bot...")
    
    # Use asyncio.run() if this is the main entry point, 
    # or integrate into an existing event loop if running with Flask/FastAPI.
    # For simplicity now, assume this runs independently.
    
    application = ApplicationBuilder().token(bot_token).post_init(post_init).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_files_command))
    application.add_handler(CommandHandler("download", download_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document)) # Handle any document
    # Consider adding handlers for photos, videos, etc. if needed
    # application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Run the bot until the user presses Ctrl-C
    print("Telegram bot started. Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    print("Telegram bot stopped.")


if __name__ == '__main__':
    # Allows running the bot directly via 'python -m amazing_storage.bot.bot'
    run_bot() 