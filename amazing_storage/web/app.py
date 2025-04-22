import os
import sys
import time
import secrets
import json
import tempfile
import shutil
import asyncio
from flask import Flask, request, jsonify, send_from_directory, render_template, abort, flash, redirect, session, url_for, send_file
from datetime import datetime, timedelta
from functools import wraps

# Make sure core components are importable
from ..core.metadata import MetadataManager
from ..core.chunk_manager import ChunkManager
from ..config import app_config
from ..chatbot.chatbot import ChatbotClient
from ..auth.auth_manager import AuthManager

# Add Dropbox imports
from dropbox import DropboxOAuth2Flow
from dropbox.oauth import OAuth2FlowResult

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16))

# Configure upload folder
UPLOAD_FOLDER = tempfile.mkdtemp(prefix='ass_uploads_')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
print(f"Flask app configured. Using temporary upload folder: {UPLOAD_FOLDER}")

# Initialize managers
metadata_manager = MetadataManager(metadata_dir="metadata")
chunk_manager = ChunkManager(metadata_manager)
chatbot_client = ChatbotClient()
auth_manager = AuthManager()

# Import share manager here to avoid circular import
from ..models.share import ShareManager

# After other route handlers but before the run function

@app.route('/share-file/<file_id>', methods=['GET', 'POST'])
def share_file(file_id):
    """Create a new share link for a file."""
    if not session.get('user_id'):
        flash('You must be logged in to share files', 'error')
        return redirect('/login')
    
    # Get the file info to make sure it exists and belongs to user
    try:
        manifest = metadata_manager.load_manifest(file_id)
        if not manifest:
            flash('File not found', 'error')
            return redirect('/dashboard')
        
        if manifest.user_id != session['user_id']:
            flash('You can only share your own files', 'error')
            return redirect('/dashboard')
            
    except Exception as e:
        flash(f'Error loading file: {str(e)}', 'error')
        return redirect('/dashboard')
    
    if request.method == 'POST':
        try:
            # Get form data with defaults
            expiry_hours = int(request.form.get('expiry_hours', 24))
            download_limit = int(request.form.get('download_limit', 0))
            password = request.form.get('password', '')
            notes = request.form.get('notes', '')
            
            # Create the share
            share_manager = ShareManager(request.host_url.rstrip('/'))
            share = share_manager.create_share(
                file_id=file_id,
                creator_id=session['user_id'],
                expiry_hours=expiry_hours,
                download_limit=download_limit,
                password=password if password else None,
                notes=notes
            )
            
            # Calculate expiry date for display
            expiry_date = datetime.fromtimestamp(share.expires_at).strftime("%Y-%m-%d %H:%M:%S") if share.expires_at > 0 else "Never"
            
            return render_template(
                'share_created.html', 
                share=share,
                filename=manifest.original_filename,
                expiry_date=expiry_date,
                share_url=share.get_share_url(request.host_url.rstrip('/')),
                is_password_protected=bool(password)
            )
            
        except Exception as e:
            flash(f'Error creating share: {str(e)}', 'error')
            return redirect(f'/dashboard')
    
    # GET request: render the share creation form
    return render_template('create_share.html', file_id=file_id, filename=manifest.original_filename)


@app.route('/share/<share_id>/<access_token>', methods=['GET', 'POST'])
def access_shared_file(share_id, access_token):
    """Access a shared file using a share link."""
    share_manager = ShareManager()
    share = share_manager.get_share(share_id, access_token)
    
    if not share:
        flash('Invalid or expired share link', 'error')
        return redirect('/')
    
    if not share.is_valid():
        flash('This share link has expired', 'error')
        return redirect('/')
    
    # Handle password verification
    if share.password_hash:
        if request.method == 'POST':
            password = request.form.get('password', '')
            if not share.verify_password(password):
                flash('Incorrect password', 'error')
                return render_template('share_password.html', share_id=share_id, access_token=access_token)
        else:
            # Show password form on GET request
            return render_template('share_password.html', share_id=share_id, access_token=access_token)
    
    try:
        # Get the file manifest
        manifest = metadata_manager.load_manifest(share.file_id)
        if not manifest:
            flash('The shared file no longer exists', 'error')
            return redirect('/')
        
        # Increment download counter for limit tracking
        share.increment_downloads()
        
        # Generate download URL with access_token as query param to authorize this specific download
        download_url = f'/share-download/{share.file_id}?token={access_token}&share={share_id}'
        
        return render_template(
            'view_shared_file.html',
            filename=manifest.original_filename,
            filesize=manifest.total_size,
            share=share,
            download_url=download_url
        )
        
    except Exception as e:
        flash(f'Error accessing shared file: {str(e)}', 'error')
        return redirect('/')


@app.route('/share-download/<file_id>')
def download_shared_file(file_id):
    """Download a file through a share link."""
    # Verify access is through a valid share link
    share_id = request.args.get('share')
    token = request.args.get('token')
    
    if not share_id or not token:
        flash('Invalid download request', 'error')
        return redirect('/')
    
    share_manager = ShareManager()
    share = share_manager.get_share(share_id, token)
    
    if not share or not share.is_valid() or share.file_id != file_id:
        flash('Invalid or expired share link', 'error')
        return redirect('/')
    
    try:
        manifest = metadata_manager.load_manifest(file_id)
        if not manifest:
            flash('The shared file no longer exists', 'error')
            return redirect('/')
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_filename = temp_file.name
        
        # Download and reconstruct the file
        chunk_manager.download_file(manifest, temp_filename)
        
        # Serve the file as an attachment
        return send_file(
            temp_filename,
            as_attachment=True,
            download_name=manifest.original_filename,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'error')
        return redirect('/')


@app.route('/my-shares')
def my_shares():
    """List all shares created by the user."""
    if not session.get('user_id'):
        flash('You must be logged in to view your shares', 'error')
        return redirect('/login')
    
    try:
        share_manager = ShareManager()
        shares = share_manager.list_shares_by_creator(session['user_id'])
        
        # Get file information for each share
        share_info = []
        for share in shares:
            try:
                manifest = metadata_manager.load_manifest(share.file_id)
                filename = manifest.original_filename if manifest else "File not found"
                
                # Calculate expiry date for display
                expiry_date = datetime.fromtimestamp(share.expires_at).strftime("%Y-%m-%d %H:%M:%S") if share.expires_at > 0 else "Never"
                
                share_info.append({
                    'share': share,
                    'filename': filename,
                    'is_valid': share.is_valid(),
                    'is_password_protected': bool(share.password_hash),
                    'expiry_date': expiry_date,
                    'share_url': share.get_share_url(request.host_url.rstrip('/'))
                })
            except Exception as e:
                print(f"Error processing share {share.share_id}: {e}")
                
        return render_template('my_shares.html', shares=share_info)
        
    except Exception as e:
        flash(f'Error loading shares: {str(e)}', 'error')
        return redirect('/dashboard')


@app.route('/delete-share/<share_id>', methods=['POST'])
def delete_share(share_id):
    """Delete a share link."""
    if not session.get('user_id'):
        flash('You must be logged in to manage your shares', 'error')
        return redirect('/login')
    
    try:
        share_manager = ShareManager()
        success = share_manager.delete_share(share_id, session['user_id'])
        
        if success:
            flash('Share link deleted successfully', 'success')
        else:
            flash('Unable to delete share link', 'error')
            
    except Exception as e:
        flash(f'Error deleting share: {str(e)}', 'error')
        
    return redirect('/my-shares')


# Administrative function to clean up expired shares
def cleanup_expired_shares_task():
    """Background task to clean up expired shares."""
    try:
        share_manager = ShareManager()
        count = share_manager.cleanup_expired_shares()
        print(f"Cleaned up {count} expired shares")
    except Exception as e:
        print(f"Error cleaning up expired shares: {e}")

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_dropbox_oauth_flow():
    """Get a DropboxOAuth2Flow configured from the app settings."""
    # --- DEBUG PRINT --- 
    print(f"[DEBUG app.py] Using dropbox_app_key: {app_config.dropbox_app_key}")
    print(f"[DEBUG app.py] Using dropbox_app_secret: {app_config.dropbox_app_secret}")
    print(f"[DEBUG app.py] Using dropbox_redirect_uri: {app_config.dropbox_redirect_uri}")
    # --- END DEBUG --- 
    
    # Check for required credentials
    if not app_config.dropbox_app_key:
        raise ValueError("Dropbox App Key not configured (ASS_DROPBOX_APP_KEY)")
    if not app_config.dropbox_app_secret:
        raise ValueError("Dropbox App Secret not configured (ASS_DROPBOX_APP_SECRET)")
    if not app_config.dropbox_redirect_uri:
        raise ValueError("Dropbox Redirect URI not configured (ASS_DROPBOX_REDIRECT_URI)")
        
    return DropboxOAuth2Flow(
        app_config.dropbox_app_key,
        consumer_secret=app_config.dropbox_app_secret,  # Must use consumer_secret parameter name
        redirect_uri=app_config.dropbox_redirect_uri,
        session=session,  # Pass the Flask session object
        csrf_token_session_key='dropbox-auth-csrf-token',
        token_access_type='offline'  # Request offline access to get refresh token
    )

@app.route('/dropbox_auth/<int:provider_index>')
def dropbox_auth_start(provider_index):
    """Starts the Dropbox OAuth 2 authorization flow."""
    if not app_config.dropbox_app_key or not app_config.dropbox_app_secret or not app_config.dropbox_redirect_uri:
        return "Error: Dropbox OAuth settings (App Key, Secret, Redirect URI) are not configured in environment variables.", 500

    # Store the provider index we are authorizing in the session
    session['dropbox_authorizing_provider_index'] = provider_index

    # Let DropboxOAuth2Flow handle CSRF protection internally
    oauth_flow = get_dropbox_oauth_flow()
    authorize_url = oauth_flow.start()  # No state parameter needed, handled internally

    # Redirect user to Dropbox for authorization
    return redirect(authorize_url)

@app.route('/dropbox_callback')
def dropbox_auth_callback():
    """Handles the redirect back from Dropbox after authorization."""
    try:
        # Retrieve the provider index from the session
        provider_index = session.pop('dropbox_authorizing_provider_index', None)
        if provider_index is None:
            return "Error: Authorization state missing (provider index). Please start the auth process again.", 400

        oauth_flow = get_dropbox_oauth_flow()
        
        # Finish the flow to get the tokens
        # CSRF validation is handled automatically by the flow
        oauth_result = oauth_flow.finish(request.args)

        # Find the corresponding DropboxStorage instance
        from ..storage.dropbox_storage import DropboxStorage 
        if provider_index >= len(chunk_manager.providers) or not isinstance(chunk_manager.providers[provider_index], DropboxStorage):
             return f"Error: Invalid provider index {provider_index} after callback.", 500

        dropbox_provider = chunk_manager.providers[provider_index]
        
        # Save the obtained tokens (including the refresh token)
        dropbox_provider._save_token_data(token_result=oauth_result)

        flash(f"Successfully authorized Dropbox account for provider {provider_index}!", "success")
        return redirect(url_for('index')) # Redirect to homepage

    except Exception as e:
        app.logger.error(f"Dropbox OAuth Error: {e}")
        return f"Error during Dropbox authorization: {e}", 500

# --- Routes ---

@app.route('/', methods=['GET'])
def index():
    """Displays the main page with the file list and upload form."""
    try:
        # Get basic file list
        file_ids_names = chunk_manager.list_files()
        
        # Enhance with chunk counts
        files_with_details = []
        for file_id, filename in file_ids_names:
            # Load manifest to get chunk information
            manifest = metadata_manager.load_manifest(file_id)
            chunk_count = 0
            if manifest is not None and hasattr(manifest, 'chunks'):
                chunk_count = len(manifest.chunks)
            
            # Add tuple with (file_id, filename, chunk_count)
            files_with_details.append((file_id, filename, chunk_count))
            
        # Sort by filename
        files_with_details.sort(key=lambda item: item[1].lower())
        
        total_providers = len(chunk_manager.providers)
        total_files = len(files_with_details)
        chunk_size_mb = app_config.chunk_size / (1024 * 1024)
        
    except Exception as e:
        app.logger.error(f"Error listing files: {e}")
        flash(f"Error listing files: {e}", "danger")
        files_with_details = []
        total_providers = 0
        total_files = 0
        chunk_size_mb = 0
    
    def get_file_icon(filename):
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        icons = {
            'pdf': 'bi-file-earmark-pdf',
            'doc': 'bi-file-earmark-word',
            'docx': 'bi-file-earmark-word',
            'xls': 'bi-file-earmark-excel',
            'xlsx': 'bi-file-earmark-excel',
            'ppt': 'bi-file-earmark-ppt',
            'pptx': 'bi-file-earmark-ppt',
            'jpg': 'bi-file-earmark-image',
            'jpeg': 'bi-file-earmark-image',
            'png': 'bi-file-earmark-image',
            'gif': 'bi-file-earmark-image',
            'zip': 'bi-file-earmark-zip',
            'rar': 'bi-file-earmark-zip',
            'txt': 'bi-file-earmark-text',
            'mp3': 'bi-file-earmark-music',
            'mp4': 'bi-file-earmark-play',
            'py': 'bi-file-earmark-code',
            'js': 'bi-file-earmark-code',
            'html': 'bi-file-earmark-code',
            'css': 'bi-file-earmark-code',
        }
        return icons.get(ext, 'bi-file-earmark')
    
    return render_template(
        'index.html', 
        files=files_with_details,
        total_providers=total_providers,
        total_files=total_files,
        chunk_size_mb=f"{chunk_size_mb:.1f}",
        get_file_icon=get_file_icon
    )

@app.route('/upload', methods=['POST'])
def upload_file_route():
    """Handles file uploads."""
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return jsonify({"error": "No file part in request"}), 400
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return jsonify({"error": "No file selected"}), 400

    if file:
        # Secure filename handling
        from werkzeug.utils import secure_filename
        filename = file.filename
        secure_name = secure_filename(filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file_id = None
        
        try:
            # Save the file with proper file handling
            file.save(temp_path)
            app.logger.info(f"File temporarily saved to: {temp_path}")
            
            # Make sure the file is closed properly before chunk manager processes it
            # Some systems need a small delay to ensure file handles are released
            time.sleep(0.1)  
            
            # Upload using ChunkManager - the chunk manager will handle its own temp files
            file_id = chunk_manager.upload_file(temp_path, original_filename=filename)
            
            # Success - remove our temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                app.logger.info(f"Temporary file removed: {temp_path}")

            # Return success response
            if file_id:
                flash(f"File '{filename}' uploaded successfully (ID: {file_id})", "success")
                return jsonify({"message": f"File '{filename}' uploaded successfully", "file_id": file_id}), 201
            else:
                raise ValueError("Upload process didn't return a valid file ID")
                
        except Exception as e:
            app.logger.error(f"Error during upload process for {filename}: {e}")
            
            # Ensure temporary file is cleaned up
            if os.path.exists(temp_path):
                try:
                    # Give the system a moment to release any file handles
                    time.sleep(0.5)
                    os.remove(temp_path)
                    app.logger.info(f"Temporary file removed after error: {temp_path}")
                except OSError as rm_err:
                    app.logger.error(f"Error removing temp file {temp_path} after error: {rm_err}")
            
            # Clean up any partial uploads if we have a file_id
            if file_id:
                try:
                    chunk_manager.delete_file(file_id)
                    app.logger.info(f"Partial upload deleted for file_id: {file_id}")
                except Exception as cleanup_err:
                    app.logger.error(f"Error cleaning up partial upload for {file_id}: {cleanup_err}")
            
            flash(f"An unexpected error occurred during upload: {e}", "danger")
            return jsonify({"error": f"An internal error occurred during upload."}), 500
    
    return jsonify({"error": "File processing failed."}), 500

@app.route('/download/<file_id>', methods=['GET'])
def download_file_route(file_id):
    """Handles file downloads."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        abort(404, description="File not found")
    
    # Check if manifest has necessary attributes
    if not hasattr(manifest, 'original_filename'):
        flash("The file has an invalid format", "danger")
        return redirect(url_for('index'))
    
    # Create a temporary directory for the downloaded file
    temp_dir = tempfile.mkdtemp(prefix='ass_downloads_')
    # Secure the filename for the path
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(manifest.original_filename)
    download_path = os.path.join(temp_dir, safe_filename)
    
    try:
        print(f"Downloading file {file_id} to temporary path: {download_path}")
        chunk_manager.download_file(file_id, download_path)
        
        print(f"Sending file: {download_path}")
        # Use send_from_directory for safer file sending
        # as_attachment=True prompts the user to download
        response = send_from_directory(temp_dir, safe_filename, as_attachment=True)
        
        @response.call_on_close
        def cleanup_temp_dir():
             try:
                  print(f"Cleaning up temporary download directory: {temp_dir}")
                  shutil.rmtree(temp_dir)
                  print(f"Successfully removed: {temp_dir}")
             except Exception as e:
                  app.logger.error(f"Error cleaning up temp download directory {temp_dir}: {e}")

        return response

    except FileNotFoundError:
         shutil.rmtree(temp_dir) # Clean up if download failed early
         abort(404, description="File manifest found, but download failed (chunk missing?)")
    except Exception as e:
        app.logger.error(f"Error during download process for {file_id}: {e}")
        shutil.rmtree(temp_dir) # Clean up on any error
        abort(500, description="An internal error occurred during download.")


@app.route('/delete/<file_id>', methods=['POST']) # Use POST for deletion actions
def delete_file_route(file_id):
    """Handles file deletion."""
    try:
        success = chunk_manager.delete_file(file_id)
        if success:
            flash(f"File (ID: {file_id}) deleted successfully.", "success")
            return jsonify({"message": f"File deleted successfully", "file_id": file_id}), 200
        else:
            flash(f"Failed to delete file (ID: {file_id}). Some chunks or manifest might remain.", "warning")
            # Even if some chunks failed, the manifest might be gone, so 200 OK might still be appropriate
            return jsonify({"message": f"File deletion process completed with warnings.", "file_id": file_id}), 200
    except Exception as e:
        app.logger.error(f"Error during deletion process for {file_id}: {e}")
        flash(f"An error occurred during deletion: {e}", "danger")
        return jsonify({"error": f"An internal error occurred during deletion."}), 500
    
@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages using the AI chatbot."""
    try:
        message = request.json.get('message', '')
        if not message:
            return jsonify({"response": "Please send a message to chat."}), 400
            
        if not chatbot_client.is_enabled():
            return jsonify({"response": "Sorry, the chatbot is not available at the moment."}), 200
            
        # Create system context about the storage system
        system_context = (
            "You are a helpful assistant for the Amazing Storage System, a Flask web app that splits uploaded files into 5MB chunks, stores them across multiple Google Drive and Dropbox accounts with versioning and metadata management, and provides a web dashboard and Telegram chatbot interface."
        )
        
        full_prompt = f"{system_context}\n\nUser question: {message}"
        
        # Get response from the chatbot - now using the synchronous call
        response = chatbot_client.get_response(full_prompt)
        
        return jsonify({"response": response}), 200
    
    except Exception as e:
        app.logger.error(f"Error in chat endpoint: {e}", exc_info=True) # Log with traceback
        # Return the error message raised from get_response or other exceptions
        return jsonify({"response": str(e)}), 500

@app.route('/versions/<file_id>', methods=['GET'])
def view_versions(file_id):
    """Display version history for a file."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        abort(404, description="File not found")
    
    # Check if manifest has versions attribute
    if not hasattr(manifest, 'versions') or not manifest.versions:
        flash("This file has no version history available", "warning")
        return redirect(url_for('index'))
    
    # Sort versions by timestamp (newest first)
    versions = sorted(manifest.versions, key=lambda v: v.timestamp, reverse=True)
    
    # Format timestamps for display
    formatted_versions = []
    for version in versions:
        timestamp = datetime.datetime.fromtimestamp(version.timestamp)
        formatted_versions.append({
            'version_id': version.version_id,
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'is_current': version.is_current,
            'notes': version.notes,
            'chunk_count': len(version.chunks),
        })
    
    return render_template(
        'versions.html', 
        file_id=file_id, 
        filename=manifest.original_filename,
        versions=formatted_versions
    )

@app.route('/restore/<file_id>/<version_id>', methods=['POST'])
def restore_version(file_id, version_id):
    """Restore a previous version of a file."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        abort(404, description="File not found")
    
    # Check if manifest has set_current_version method
    if not hasattr(manifest, 'set_current_version'):
        flash(f"The file does not support version management", "danger")
        return redirect(url_for('index'))
    
    # Set the specified version as current
    if manifest.set_current_version(version_id):
        # Save the updated manifest
        metadata_manager.save_manifest(manifest)
        flash(f"Version restored successfully for '{manifest.original_filename}'", "success")
    else:
        flash(f"Failed to restore version. Version ID not found.", "danger")
    
    return redirect(f'/versions/{file_id}')

@app.route('/update/<file_id>', methods=['GET', 'POST'])
def update_file(file_id):
    """Handles uploading a new version of a file."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        abort(404, description="File not found")
    
    # Check if manifest has necessary attributes
    if not hasattr(manifest, 'original_filename'):
        flash("The file does not support version updates", "danger")
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(f'/versions/{file_id}')
        
        file = request.files['file']
        version_notes = request.form.get('version_notes', '')
        
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(f'/versions/{file_id}')
        
        if file:
            # Save temporarily locally before chunking
            from werkzeug.utils import secure_filename
            filename = file.filename
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
            
            try:
                file.save(temp_path)
                app.logger.info(f"File temporarily saved to: {temp_path}")
                
                # Upload new version
                chunk_manager.upload_file(
                    temp_path, 
                    original_filename=manifest.original_filename,
                    file_id=file_id,
                    version_notes=version_notes
                )
                
                # Clean up temporary file
                os.remove(temp_path)
                app.logger.info(f"Temporary file removed: {temp_path}")
                
                flash(f"New version of '{manifest.original_filename}' uploaded successfully", "success")
                return redirect(f'/versions/{file_id}')
                
            except Exception as e:
                app.logger.error(f"Error during version upload: {e}")
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                flash(f"An unexpected error occurred during upload: {e}", "danger")
                return redirect(f'/versions/{file_id}')
    
    # GET request - show upload form
    return render_template(
        'update.html', 
        file_id=file_id, 
        filename=manifest.original_filename
    )

# --- API Endpoints for Mobile App --- 

@app.route('/api/files', methods=['GET'])
def api_list_files():
    """API endpoint to list stored files."""
    try:
        # Use the existing chunk_manager method which gets data from metadata
        stored_files_tuples = chunk_manager.list_files()
        # Sort by filename 
        stored_files_tuples.sort(key=lambda item: item[1].lower())
        
        # Format the data as a list of dictionaries for JSON
        files_json = [{'id': file_id, 'name': filename} for file_id, filename in stored_files_tuples]
        
        return jsonify(files=files_json), 200
        
    except Exception as e:
        app.logger.error(f"Error in /api/files endpoint: {e}", exc_info=True)
        return jsonify({"error": "Failed to retrieve file list", "details": str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def api_upload_file():
    """API endpoint to handle file uploads from mobile/clients."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file:
        # Secure filename handling is important 
        from werkzeug.utils import secure_filename
        # Use original filename for metadata, secure name for temp storage
        original_filename = file.filename 
        safe_temp_filename = secure_filename(original_filename) 
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_temp_filename)

        try:
            file.save(temp_path)
            app.logger.info(f"API Upload: File temporarily saved to: {temp_path}")

            # Upload using ChunkManager, providing the original filename
            file_id = chunk_manager.upload_file(temp_path, original_filename=original_filename)

            # Clean up temporary file immediately 
            os.remove(temp_path)
            app.logger.info(f"API Upload: Temporary file removed: {temp_path}")

            if file_id:
                return jsonify({"message": f"File '{original_filename}' uploaded successfully", "file_id": file_id}), 201
            else:
                # upload_file should ideally raise an exception on failure, 
                # but handle the case where it might return None/empty
                return jsonify({"error": f"Failed to upload file '{original_filename}'. ChunkManager returned no ID."}), 500

        except Exception as e:
            app.logger.error(f"Error during API upload process for {original_filename}: {e}", exc_info=True)
            # Ensure temporary file is cleaned up even on error
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    app.logger.info(f"API Upload: Temporary file removed after error: {temp_path}")
                except OSError as rm_err:
                    app.logger.error(f"API Upload: Error removing temp file {temp_path} after error: {rm_err}")
            return jsonify({"error": f"An internal error occurred during upload.", "details": str(e)}), 500

    return jsonify({"error": "File processing failed."}), 500

@app.route('/api/download/<file_id>', methods=['GET'])
def api_download_file(file_id):
    """API endpoint to handle file downloads."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        # Use 404 directly for API not found errors
        return jsonify({"error": "File not found"}), 404 
    
    # Check if manifest has necessary attributes
    if not hasattr(manifest, 'original_filename'):
        return jsonify({"error": "Invalid file manifest format"}), 500
    
    # Create a temporary directory for the downloaded file
    temp_dir = tempfile.mkdtemp(prefix='ass_api_downloads_') 
    # Secure the filename for the path
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(manifest.original_filename)
    download_path = os.path.join(temp_dir, safe_filename)

    try:
        app.logger.info(f"API Download: Downloading file {file_id} to temporary path: {download_path}")
        # Use the chunk manager to reassemble the file
        chunk_manager.download_file(file_id, download_path)
        app.logger.info(f"API Download: File reassembled at {download_path}")

        # Use send_from_directory for safer file sending
        # as_attachment=True helps suggest download, but client might handle it differently
        response = send_from_directory(temp_dir, safe_filename, as_attachment=True)

        @response.call_on_close
        def cleanup_temp_dir():
            try:
                app.logger.info(f"API Download: Cleaning up temporary directory: {temp_dir}")
                shutil.rmtree(temp_dir)
                app.logger.info(f"API Download: Successfully removed: {temp_dir}")
            except Exception as e:
                app.logger.error(f"API Download: Error cleaning up temp download directory {temp_dir}: {e}")

        return response

    except FileNotFoundError as e: # Catch specific error from chunk_manager
        shutil.rmtree(temp_dir) # Clean up if download failed 
        app.logger.error(f"API Download: FileNotFoundError for {file_id}: {e}")
        return jsonify({"error": "File download failed, possibly missing chunks", "details": str(e)}), 404
    except Exception as e:
        app.logger.error(f"Error during API download process for {file_id}: {e}", exc_info=True)
        # Ensure cleanup on any error
        try:
            shutil.rmtree(temp_dir)
        except Exception as cleanup_err:
             app.logger.error(f"API Download: Error cleaning up temp dir {temp_dir} after download error: {cleanup_err}")
        return jsonify({"error": "An internal error occurred during download", "details": str(e)}), 500

@app.route('/api/delete/<file_id>', methods=['DELETE'])
def api_delete_file(file_id):
    """API endpoint to handle file deletion."""
    try:
        # Attempt to delete the file using the chunk manager
        # This handles deleting chunks from providers and the manifest
        success = chunk_manager.delete_file(file_id)
        
        if success:
            # Even if warnings occurred during chunk deletion, the manifest is likely gone.
            # Return success. The client can infer potential issues if needed elsewhere.
            app.logger.info(f"API Delete: Successfully processed deletion for file ID {file_id}")
            return jsonify({"message": "File deleted successfully", "file_id": file_id}), 200
        else:
            # This case might occur if manifest deletion failed after chunk errors
            app.logger.warning(f"API Delete: Deletion process for {file_id} completed with warnings/errors.")
            return jsonify({"message": "File deletion completed with warnings", "file_id": file_id}), 200 # Still OK, operation attempted
            
    except FileNotFoundError:
        # If load_manifest inside delete_file raises this (though current logic handles it)
        app.logger.info(f"API Delete: File ID {file_id} not found for deletion.")
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        app.logger.error(f"Error during API delete process for {file_id}: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred during deletion.", "details": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API endpoint to handle chatbot interactions."""
    try:
        message = request.json.get('message', '')
        if not message:
            return jsonify({"error": "No message provided"}), 400

        if not chatbot_client.is_enabled():
            return jsonify({"response": "Chatbot is not available"}), 200 # Not an error, just disabled

        # Create system context (optional, but good practice)
        system_context = (
            "You are a helpful assistant for the Amazing Storage System."
        )
        full_prompt = f"{system_context}\n\nUser: {message}"

        # Get response from the synchronous chatbot client method
        response_text = chatbot_client.get_response(full_prompt)

        return jsonify({"response": response_text}), 200

    except RuntimeError as e:
        # Catch the specific error raised by get_response on failure
        app.logger.error(f"Error in /api/chat endpoint (RuntimeError): {e}", exc_info=True)
        return jsonify({"error": "Chatbot interaction failed", "details": str(e)}), 500
    except Exception as e:
        # Catch any other unexpected errors
        app.logger.error(f"Error in /api/chat endpoint: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred", "details": str(e)}), 500

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # For demo, just accept any input
        session['user_id'] = 'demo_user'
        session['username'] = username
        session['role'] = 'user'
        flash(f'Welcome, {username}!', 'success')
        return redirect(url_for('index'))
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Simple validation
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return render_template('register.html')
        
        # For demo, just accept registration
        flash(f'Account successfully created for {username}. Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Display the user dashboard with account status and storage statistics"""
    message = request.args.get('message', '')
    
    # Get basic file list and storage stats
    try:
        file_ids_names = chunk_manager.list_files()
        
        # Enhance with chunk counts
        files_with_details = []
        for file_id, filename in file_ids_names:
            # Load manifest to get chunk information
            manifest = metadata_manager.load_manifest(file_id)
            chunk_count = 0
            if manifest is not None and hasattr(manifest, 'chunks'):
                chunk_count = len(manifest.chunks)
            
            # Add tuple with (file_id, filename, chunk_count)
            files_with_details.append((file_id, filename, chunk_count))
            
        # Sort by filename
        files_with_details.sort(key=lambda item: item[1].lower())
        
        total_providers = len(chunk_manager.providers)
        total_files = len(files_with_details)
        chunk_size_mb = app_config.chunk_size / (1024 * 1024)
        
    except Exception as e:
        app.logger.error(f"Error loading dashboard data: {e}")
        flash(f"Error loading dashboard data: {e}", "danger")
        files_with_details = []
        total_providers = 0
        total_files = 0
        chunk_size_mb = 0
    
    # Get file icon helper function
    def get_file_icon(filename):
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        icons = {
            'pdf': 'bi-file-earmark-pdf',
            'doc': 'bi-file-earmark-word',
            'docx': 'bi-file-earmark-word',
            'xls': 'bi-file-earmark-excel',
            'xlsx': 'bi-file-earmark-excel',
            'ppt': 'bi-file-earmark-ppt',
            'pptx': 'bi-file-earmark-ppt',
            'jpg': 'bi-file-earmark-image',
            'jpeg': 'bi-file-earmark-image',
            'png': 'bi-file-earmark-image',
            'gif': 'bi-file-earmark-image',
            'zip': 'bi-file-earmark-zip',
            'rar': 'bi-file-earmark-zip',
            'txt': 'bi-file-earmark-text',
            'mp3': 'bi-file-earmark-music',
            'mp4': 'bi-file-earmark-play',
            'py': 'bi-file-earmark-code',
            'js': 'bi-file-earmark-code',
            'html': 'bi-file-earmark-code',
            'css': 'bi-file-earmark-code',
        }
        return icons.get(ext, 'bi-file-earmark')
    
    return render_template(
        'dashboard.html',
        files=files_with_details,
        total_providers=total_providers,
        total_files=total_files,
        chunk_size_mb=f"{chunk_size_mb:.1f}",
        get_file_icon=get_file_icon,
        message=message
    )

def run_app():
    print(f"Flask development server starting on http://{app_config.web_interface_host}:{app_config.web_interface_port}")
    app.run(host=app_config.web_interface_host, port=app_config.web_interface_port, debug=True)

if __name__ == '__main__':
     run_app()
