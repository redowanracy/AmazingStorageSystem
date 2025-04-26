import logging
import os
import tempfile
import asyncio
import traceback
import re
from typing import List, Tuple, Dict, Set, Optional

from telegram import Update, BotCommand, InputFile
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Relative imports from parent directories
from ..config import app_config
from ..core.metadata import MetadataManager
from ..core.chunk_manager import ChunkManager
from ..chatbot.chatbot import ChatbotClient
from ..core.file_processor import FileProcessor

# Basic logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Initialize core components
metadata_manager_bot = MetadataManager(metadata_dir="metadata")
chunk_manager_bot = ChunkManager(metadata_manager_bot)
chatbot_client = ChatbotClient()
file_processor = FileProcessor(metadata_manager_bot, chunk_manager_bot)

# Set file processor for chatbot
chatbot_client.set_file_processor(file_processor)

# Track active file contexts per user
user_active_files: Dict[int, Set[str]] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I'm the Amazing Storage Bot. "
        rf"Send me a file to upload it, or use /help to see commands.",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists available commands."""
    help_text = (
        "Available commands:\n"
        "/list - List all stored files\n"
        "/download <file_id> - Download a file by its ID\n"
        "/delete <file_id> - Delete a file by its ID\n"
        "/context - Manage files in your AI context\n"
        "\nFile Context Features:\n"
        "- Upload any document to add it to your AI context automatically\n"
        "- Send text messages to ask questions about your uploaded files\n"
        "- Use /context to view, add, remove, or clear files from your context\n"
        "- Supported file formats for AI context: PDF, TXT, DOCX, DOC\n"
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
        files.sort(key=lambda item: item[1].lower())

        # Function to escape HTML characters for safe display
        def escape_html(text: str) -> str:
            return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        for file_id, filename in files:
            safe_filename = escape_html(filename)
            safe_file_id = escape_html(file_id)
            message += f"- <code>{safe_filename}</code>\n  ID: <code>{safe_file_id}</code>\n"

        # Truncate message if it exceeds Telegram's limit (4096 chars)
        if len(message) > 4096:
             message = message[:4000] + "\n... (list truncated)"

        await update.message.reply_html(message)

    except Exception as e:
        logger.error(f"Error listing files for user {update.effective_user.id}: {e}", exc_info=True)
        await update.message.reply_text(f"Sorry, an error occurred while listing files: {e}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles file uploads and processes them for AI context."""
    if not update.message or not update.message.document:
        logger.warning("Received non-document message in document handler.")
        return

    user_id = update.effective_user.id
    doc = update.message.document
    original_filename = doc.file_name
    file_size = doc.file_size

    logger.info(f"User {user_id} is uploading '{original_filename}' (Size: ~{file_size / (1024*1024):.2f} MB)")
    await update.message.reply_text(f"Received '{original_filename}'. Starting upload process...")

    temp_dir = tempfile.mkdtemp(prefix='ass_bot_upload_')
    temp_path = os.path.join(temp_dir, original_filename)
    file_id_telegram = doc.file_id

    try:
        # Indicate the bot is processing
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_document")
        
        bot = context.bot
        file_telegram = await bot.get_file(file_id_telegram)
        logger.info(f"Downloading Telegram file {file_id_telegram} to {temp_path}")
        await file_telegram.download_to_drive(temp_path)
        logger.info(f"Downloaded successfully.")

        logger.info(f"Starting chunked upload for {temp_path}")
        uploaded_file_id = chunk_manager_bot.upload_file(temp_path, original_filename=original_filename)

        if uploaded_file_id:
            logger.info(f"Successfully uploaded '{original_filename}' for user {user_id}. File ID: {uploaded_file_id}")
            
            # Add file to user's active files for LLM context
            if user_id not in user_active_files:
                user_active_files[user_id] = set()
            user_active_files[user_id].add(uploaded_file_id)
            
            # Add file to chatbot context
            success, message = chatbot_client.add_file_to_context(str(user_id), uploaded_file_id)
            
            # Check if file is supported for text extraction
            file_ext = original_filename.split('.')[-1].lower() if '.' in original_filename else ''
            supported_formats = ['pdf', 'txt', 'docx', 'doc']
            
            if file_ext in supported_formats:
                context_status = "File added to AI context. You can now ask questions about it!" if success else f"Note: {message}"
            else:
                context_status = f"Note: File format '.{file_ext}' may not be fully supported for AI context. Supported formats: PDF, TXT, DOCX."
            
            await update.message.reply_text(
                f"Successfully uploaded '{original_filename}'\nFile ID: `{uploaded_file_id}`\n\n{context_status}",
                parse_mode='MarkdownV2' # Use Markdown for backticks around ID
            )
        else:
            logger.error(f"Chunked upload failed for '{original_filename}' from user {user_id}.")
            await update.message.reply_text(f"Sorry, the upload of '{original_filename}' failed. Please check the logs or try again.")

    except Exception as e:
        logger.error(f"Error processing upload for '{original_filename}' from user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred during upload: {e}")
    finally:
        # Clean up temporary resources
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
    # Use secure_filename to prevent path traversal or other issues, even if filename comes from trusted manifest
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(manifest.original_filename)
    download_path = os.path.join(temp_dir, safe_filename)

    try:
        logger.info(f"Downloading file {file_id_to_download} to temp path {download_path}")
        chunk_manager_bot.download_file(file_id_to_download, download_path)
        logger.info(f"File reassembled locally at {download_path}")

        # Check file size before sending (Telegram has limits, often 50MB for bots)
        file_size = os.path.getsize(download_path)
        if file_size > 50 * 1024 * 1024: # 50MB limit
             logger.warning(f"File {download_path} ({file_size} bytes) exceeds Telegram bot limit.")
             await update.message.reply_text(f"Sorry, '{manifest.original_filename}' is too large ({file_size / (1024*1024):.1f}MB) to send back via Telegram.")
             return

        # Send the document with increased timeouts for potentially large files
        await update.message.reply_text("Reassembly complete. Sending file back to you now...")
        with open(download_path, 'rb') as doc_file:
            await update.message.reply_document(
                document=doc_file,
                filename=manifest.original_filename,
                read_timeout=60, # Increased read timeout (default is 20s)
                write_timeout=60 # Increased write timeout (default is 20s)
            )
        logger.info(f"Successfully sent file {file_id_to_download} to user {user_id}.")

    except FileNotFoundError as e:
        logger.error(f"Download failed for user {user_id}, file ID {file_id_to_download}: {e}", exc_info=True)
        await update.message.reply_text(f"Download failed: A required chunk might be missing or the manifest is invalid.")
    except Exception as e:
        logger.error(f"Error processing download for {file_id_to_download} from user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred during download: {e}")
    finally:
        # Clean up temporary resources
        try:
            if os.path.exists(download_path):
                os.remove(download_path)
            if os.path.exists(temp_dir):
                # Use shutil.rmtree for potentially non-empty dirs if errors occur, but rmdir is safer first
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

    # Check if file exists first to provide a better user message
    manifest = metadata_manager_bot.load_manifest(file_id_to_delete)
    original_name = manifest.original_filename if manifest else "(unknown name)"

    try:
        success = chunk_manager_bot.delete_file(file_id_to_delete)
        if success:
            logger.info(f"Successfully deleted file ID {file_id_to_delete} (name: {original_name}) for user {user_id}.")
            await update.message.reply_text(f"Successfully deleted file '{original_name}' (ID: {file_id_to_delete}).")
        else:
            # delete_file returns False if manifest/chunks don't exist or partial deletion fails
            logger.warning(f"Deletion attempt for file ID {file_id_to_delete} reported issues or file not found (user {user_id}).")
            if manifest: # Manifest existed but deletion failed somehow
                await update.message.reply_text(f"Deletion process for '{original_name}' completed, but there might have been issues deleting some parts. The manifest file should be gone.")
            else: # Manifest never existed
                 await update.message.reply_text(f"File ID '{file_id_to_delete}' not found. Nothing deleted.")

    except Exception as e:
        logger.error(f"Error processing deletion for {file_id_to_delete} from user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred during deletion: {e}")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles regular text messages by sending them to the chatbot with file context."""
    if not update.message or not update.message.text:
        return # Should not happen with the filter used

    user_id = update.effective_user.id
    prompt = update.message.text
    logger.info(f"User {user_id} sent text message: '{prompt[:50]}...'")

    if not chatbot_client.is_enabled():
        logger.warning("Chatbot is disabled, ignoring text message.")
        await update.message.reply_text(
            "Sorry, the AI assistant is not currently enabled. Please check your configuration or try again later."
        )
        return

    # Indicate the bot is processing
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Check if user has active file contexts
        has_context = user_id in user_active_files and len(user_active_files[user_id]) > 0
        
        if has_context:
            file_count = len(user_active_files[user_id])
            logger.info(f"User {user_id} has {file_count} active file contexts")
            
            # Get file names for context information
            file_names = []
            for file_id in user_active_files[user_id]:
                manifest = metadata_manager_bot.load_manifest(file_id)
                if manifest:
                    file_names.append(manifest.original_filename)
            
            # If this appears to be a question about uploaded files
            file_related_keywords = ['file', 'document', 'pdf', 'text', 'content', 'read', 'extract', 'information']
            is_file_question = any(keyword in prompt.lower() for keyword in file_related_keywords)
            
            if is_file_question and not file_names:
                # User might be asking about files but we don't have names
                context_info = f"(Using {file_count} uploaded files as context)"
            elif is_file_question and file_names:
                # User is asking about files and we have names
                files_str = ", ".join([f"'{name}'" for name in file_names[:3]])
                if len(file_names) > 3:
                    files_str += f" and {len(file_names) - 3} more"
                context_info = f"(Using files as context: {files_str})"
            else:
                context_info = ""
            
            # Get response from LLM with user's file context
            response_text = chatbot_client.get_response(prompt, str(user_id))
            
            # Add context info if relevant
            if context_info and not response_text.startswith("Sorry"):
                response_text = f"{context_info}\n\n{response_text}"
        else:
            # No file context available
            if any(word in prompt.lower() for word in ['file', 'document', 'pdf', 'upload']):
                # User might be asking about files but has none uploaded
                await update.message.reply_text(
                    "You don't have any files uploaded for context. Please upload a document first, then ask questions about it."
                )
                return
            
            # Regular response without file context
            response_text = chatbot_client.get_response(prompt, str(user_id))
        
        # Send the chatbot's response back
        await update.message.reply_text(response_text)
    except Exception as e:
        logger.error(f"Error getting chatbot response for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error trying to process your request. Please try again later.")




async def file_context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manages file contexts for the conversation."""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 1:
        # Show current active files
        if user_id in user_active_files and user_active_files[user_id]:
            active_files = []
            for file_id in user_active_files[user_id]:
                manifest = metadata_manager_bot.load_manifest(file_id)
                if manifest:
                    active_files.append(f"- {manifest.original_filename} (ID: {file_id})")
            
            await update.message.reply_text(
                f"Your active file contexts ({len(active_files)}):\n" + "\n".join(active_files) + 
                "\n\nUsage:\n/context add <file_id> - Add a file to context\n/context remove <file_id> - Remove a file from context\n/context clear - Clear all file contexts"
            )
        else:
            await update.message.reply_text(
                "You don't have any active file contexts.\n\n" +
                "Upload a file or use /context add <file_id> to add a file to the conversation context."
            )
        return
    
    action = context.args[0].lower()
    
    if action == "add" and len(context.args) >= 2:
        file_id = context.args[1]
        manifest = metadata_manager_bot.load_manifest(file_id)
        
        if not manifest:
            await update.message.reply_text(f"File with ID {file_id} not found.")
            return
        
        # Add to user's active files
        if user_id not in user_active_files:
            user_active_files[user_id] = set()
        user_active_files[user_id].add(file_id)
        
        # Add to chatbot context
        success, message = chatbot_client.add_file_to_context(str(user_id), file_id)
        
        if success:
            await update.message.reply_text(f"Added '{manifest.original_filename}' to your conversation context. You can now ask questions about it!")
        else:
            await update.message.reply_text(f"Error adding file to context: {message}")
    
    elif action == "remove" and len(context.args) >= 2:
        file_id = context.args[1]
        
        if user_id in user_active_files and file_id in user_active_files[user_id]:
            user_active_files[user_id].remove(file_id)
            chatbot_client.remove_file_from_context(str(user_id), file_id)
            
            manifest = metadata_manager_bot.load_manifest(file_id)
            filename = manifest.original_filename if manifest else file_id
            
            await update.message.reply_text(f"Removed '{filename}' from your conversation context.")
        else:
            await update.message.reply_text(f"File with ID {file_id} is not in your active context.")
    
    elif action == "clear":
        if user_id in user_active_files:
            # Remove all files from context
            for file_id in list(user_active_files[user_id]):
                chatbot_client.remove_file_from_context(str(user_id), file_id)
            
            user_active_files[user_id] = set()
            await update.message.reply_text("Cleared all files from your conversation context.")
        else:
            await update.message.reply_text("You don't have any active file contexts.")
    
    else:
        await update.message.reply_text(
            "Invalid command. Usage:\n" +
            "/context - Show active file contexts\n" +
            "/context add <file_id> - Add a file to context\n" +
            "/context remove <file_id> - Remove a file from context\n" +
            "/context clear - Clear all file contexts"
        )

async def post_init(application: Application):
    """Sets the bot commands list after initialization."""
    commands = [
        BotCommand("start", "Start interacting with the bot"),
        BotCommand("help", "Show available commands"),
        BotCommand("list", "List stored files"),
        BotCommand("download", "Download a file by ID (e.g., /download <file_id>)"),
        BotCommand("delete", "Delete a file by ID (e.g., /delete <file_id>)"),
        BotCommand("context", "Manage file contexts for conversation"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set.")

    # Add message handlers here - post_init ensures the Application object is fully ready
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document)) # Handle any document
    # Add the text message handler - Filters.TEXT & ~filters.COMMAND ensures it only catches non-command text
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    # Potential future handlers:
    # application.add_handler(MessageHandler(filters.PHOTO, handle_photo))


def run_bot():
    """Configures and runs the Telegram bot."""
    bot_token = app_config.telegram_bot_token
    if not bot_token:
        logger.error("Telegram bot token (ASS_TELEGRAM_BOT_TOKEN) not found. Bot cannot start.")
        print("Error: Telegram bot token not configured.")
        return

    logger.info("Starting Telegram bot...")

    # Build the application, adding post_init hook
    application = ApplicationBuilder().token(bot_token).post_init(post_init).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_files_command))
    application.add_handler(CommandHandler("download", download_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("context", file_context_command))
    # Message handlers are added in post_init

    # Start polling for updates
    print("Telegram bot started. Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    print("Telegram bot stopped.")


if __name__ == '__main__':
    # Allows running the bot directly via 'python -m amazing_storage.bot.bot'
    run_bot()