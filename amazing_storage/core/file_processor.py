import os
import tempfile
import logging
import mimetypes
import re
import PyPDF2
import docx
from typing import Dict, Optional, Tuple

from ..core.metadata import MetadataManager
from ..core.chunk_manager import ChunkManager

logger = logging.getLogger(__name__)

class FileProcessor:
    """Processes files to extract text content for LLM context."""

    def __init__(self, metadata_manager: MetadataManager, chunk_manager: ChunkManager):
        self.metadata_manager = metadata_manager
        self.chunk_manager = chunk_manager
        self.file_content_cache: Dict[str, str] = {}

    def extract_text_from_file(self, file_path: str) -> str:
        """Extract text content from a file based on its type."""
        mime_type, _ = mimetypes.guess_type(file_path)
        
        try:
            # Handle PDFs
            if file_path.lower().endswith('.pdf'):
                return self._extract_from_pdf(file_path)
            
            # Handle Word documents
            elif file_path.lower().endswith(('.docx', '.doc')):
                return self._extract_from_docx(file_path)
            
            # Handle text files
            elif mime_type and mime_type.startswith('text/'):
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
            
            # Handle other common file types
            else:
                # For now, just return a message for unsupported file types
                logger.warning(f"Unsupported file type for {file_path}")
                return f"This file type is not currently supported for text extraction: {os.path.basename(file_path)}"
        
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}", exc_info=True)
            return f"Error processing file: {str(e)}"

    def _extract_from_pdf(self, file_path: str) -> str:
        """Extract text from a PDF file."""
        text = ""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    text += reader.pages[page_num].extract_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}", exc_info=True)
            return f"Error processing PDF: {str(e)}"

    def _extract_from_docx(self, file_path: str) -> str:
        """Extract text from a Word document."""
        try:
            doc = docx.Document(file_path)
            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path}: {e}", exc_info=True)
            return f"Error processing Word document: {str(e)}"

    def get_file_content(self, file_id: str) -> Tuple[str, str]:
        """Get the content of a file by its ID.
        
        Returns:
            Tuple containing (filename, file_content)
        """
        # Check if content is already cached
        if file_id in self.file_content_cache:
            manifest = self.metadata_manager.load_manifest(file_id)
            return manifest.original_filename, self.file_content_cache[file_id]
        
        # Get file info
        manifest = self.metadata_manager.load_manifest(file_id)
        if not manifest:
            return "", f"File with ID {file_id} not found."
        
        # Create temp directory for download
        temp_dir = tempfile.mkdtemp(prefix='ass_file_processor_')
        temp_path = os.path.join(temp_dir, manifest.original_filename)
        
        try:
            # Download the file
            self.chunk_manager.download_file(file_id, temp_path)
            
            # Extract text content
            content = self.extract_text_from_file(temp_path)
            
            # Cache the content
            self.file_content_cache[file_id] = content
            
            return manifest.original_filename, content
        
        except Exception as e:
            logger.error(f"Error processing file {file_id}: {e}", exc_info=True)
            return manifest.original_filename, f"Error processing file: {str(e)}"
        
        finally:
            # Clean up
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except OSError as e:
                logger.error(f"Error cleaning up temp files: {e}")

    def clear_cache(self, file_id: Optional[str] = None):
        """Clear the file content cache for a specific file or all files."""
        if file_id:
            if file_id in self.file_content_cache:
                del self.file_content_cache[file_id]
        else:
            self.file_content_cache.clear()