import os
import tempfile
import shutil
import json
import asyncio
from flask import Flask, request, jsonify, send_from_directory, render_template_string, abort, flash, redirect
import datetime

# Make sure core components are importable
from ..core.metadata import MetadataManager
from ..core.chunk_manager import ChunkManager
from ..config import app_config
from ..chatbot.chatbot import ChatbotClient

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Use a permanent directory for actual metadata, not the test one
metadata_manager = MetadataManager(metadata_dir="metadata") 
chunk_manager = ChunkManager(metadata_manager)

# Configure a temporary directory for uploads
# For production, consider a more robust temporary storage solution
UPLOAD_FOLDER = tempfile.mkdtemp(prefix='ass_uploads_')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
print(f"Flask app configured. Using temporary upload folder: {UPLOAD_FOLDER}")

# Initialize chatbot
chatbot_client = ChatbotClient()

# --- Basic HTML Templates (Inline for Simplicity) ---
# In a real app, use separate HTML files and Jinja2 templating

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Amazing Storage System</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
  <style>
    :root {
      --primary: #4f46e5;
      --primary-hover: #4338ca;
      --danger: #ef4444;
      --danger-hover: #dc2626;
      --success: #10b981;
      --dark: #1f2937;
      --light: #f9fafb;
      --gray: #9ca3af;
      --border: #e5e7eb;
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: 'Inter', sans-serif;
      background-color: #f3f4f6;
      color: #374151;
      line-height: 1.5;
    }
    
    .container {
      max-width: 900px;
      margin: 2rem auto;
      background: white;
      border-radius: 10px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
      overflow: hidden;
    }
    
    .header {
      background-color: var(--primary);
      color: white;
      padding: 1.5rem 2rem;
    }
    
    .content {
      padding: 2rem;
    }
    
    h1 {
      font-weight: 700;
      font-size: 1.75rem;
      margin-bottom: 0;
    }
    
    h2 {
      font-weight: 600;
      font-size: 1.25rem;
      margin-bottom: 1rem;
      color: var(--dark);
    }
    
    .alert {
      padding: 1rem;
      margin-bottom: 1.5rem;
      border-radius: 6px;
    }
    
    .alert-success {
      background-color: rgba(16, 185, 129, 0.1);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.2);
    }
    
    .alert-danger {
      background-color: rgba(239, 68, 68, 0.1);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.2);
    }
    
    .upload-form {
      background-color: var(--light);
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 2rem;
      border: 1px solid var(--border);
    }
    
    .file-input-container {
      display: flex;
      align-items: center;
      margin-bottom: 1rem;
    }
    
    .file-input {
      flex: 1;
    }
    
    .btn {
      display: inline-block;
      padding: 0.5rem 1rem;
      font-weight: 500;
      text-align: center;
      white-space: nowrap;
      vertical-align: middle;
      cursor: pointer;
      border: none;
      border-radius: 6px;
      font-size: 0.875rem;
      transition: all 0.2s ease;
      text-decoration: none;
    }
    
    .btn-primary {
      background-color: var(--primary);
      color: white;
    }
    
    .btn-primary:hover {
      background-color: var(--primary-hover);
    }
    
    .btn-danger {
      background-color: var(--danger);
      color: white;
    }
    
    .btn-danger:hover {
      background-color: var(--danger-hover);
    }
    
    .file-table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    
    .file-table th {
      text-align: left;
      padding: 1rem;
      background-color: var(--light);
      font-weight: 600;
      color: var(--dark);
      border-bottom: 1px solid var(--border);
    }
    
    .file-table td {
      padding: 1rem;
      border-bottom: 1px solid var(--border);
    }
    
    .file-table tr:last-child td {
      border-bottom: none;
    }
    
    .file-table tr:hover {
      background-color: rgba(243, 244, 246, 0.5);
    }
    
    .actions {
      display: flex;
      gap: 0.5rem;
    }
    
    .empty-state {
      text-align: center;
      padding: 2rem;
      color: var(--gray);
      background-color: var(--light);
      border-radius: 8px;
      border: 1px dashed var(--border);
    }
    
    .footer {
      text-align: center;
      padding: 1rem;
      font-size: 0.875rem;
      color: var(--gray);
      border-top: 1px solid var(--border);
    }
    
    /* Dashboard styles */
    .dashboard {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }
    
    .stat-card {
      background-color: white;
      border-radius: 8px;
      padding: 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      border: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
    }
    
    .stat-value {
      font-size: 2rem;
      font-weight: 700;
      margin: 0.5rem 0;
      color: var(--primary);
    }
    
    .stat-label {
      color: var(--gray);
      font-size: 0.875rem;
    }
    
    .stat-icon {
      font-size: 1.5rem;
      color: var(--primary);
      margin-bottom: 0.5rem;
    }
    
    /* Chat widget styles */
    .chat-widget {
      position: fixed;
      bottom: 20px;
      right: 20px;
      width: 350px;
      max-height: 500px;
      background-color: white;
      border-radius: 10px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      display: flex;
      flex-direction: column;
      z-index: 1000;
      overflow: hidden;
      transition: all 0.3s ease;
    }
    
    .chat-widget.collapsed {
      height: 50px;
      overflow: hidden;
    }
    
    .chat-header {
      padding: 12px 16px;
      background-color: var(--primary);
      color: white;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: 350px;
    }
    
    .message {
      padding: 10px 12px;
      border-radius: 18px;
      max-width: 80%;
      word-break: break-word;
    }
    
    .message.user {
      background-color: var(--primary);
      color: white;
      align-self: flex-end;
      border-bottom-right-radius: 4px;
    }
    
    .message.bot {
      background-color: var(--light);
      border: 1px solid var(--border);
      align-self: flex-start;
      border-bottom-left-radius: 4px;
    }
    
    .chat-input {
      display: flex;
      padding: 10px;
      border-top: 1px solid var(--border);
    }
    
    .chat-input input {
      flex: 1;
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 20px;
      outline: none;
    }
    
    .chat-input button {
      background-color: var(--primary);
      color: white;
      border: none;
      border-radius: 50%;
      width: 36px;
      height: 36px;
      margin-left: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    .loader {
      display: inline-block;
      width: 15px;
      height: 15px;
      border: 2px solid rgba(255,255,255,0.3);
      border-radius: 50%;
      border-top-color: white;
      animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    /* Add tabs for upload and files */
    .tabs {
      display: flex;
      border-bottom: 1px solid var(--border);
      margin-bottom: 1.5rem;
    }
    
    .tab {
      padding: 0.75rem 1.5rem;
      cursor: pointer;
      font-weight: 500;
      border-bottom: 2px solid transparent;
    }
    
    .tab.active {
      border-bottom-color: var(--primary);
      color: var(--primary);
    }
    
    .tab-content {
      display: none;
    }
    
    .tab-content.active {
      display: block;
    }
    
    /* File preview styles */
    .file-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      background-color: var(--light);
      border-radius: 4px;
      margin-right: 10px;
      font-size: 1.2rem;
      color: var(--dark);
    }
    
    .file-name-cell {
      display: flex;
      align-items: center;
    }
    
    .file-id {
      color: #777;
      margin-top: 5px;
    }
    
    .version-actions {
      margin: 20px 0;
    }
    
    .version-list {
      margin-top: 20px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Amazing Storage System</h1>
    </div>
    
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}
            <div class="alert alert-{{ category }}">{{ message }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      
      <!-- Dashboard stats -->
      <div class="dashboard">
        <div class="stat-card">
          <div class="stat-icon"><i class="bi bi-hdd-stack"></i></div>
          <div class="stat-value">{{ total_providers }}</div>
          <div class="stat-label">Storage Providers</div>
        </div>
        <div class="stat-card">
          <div class="stat-icon"><i class="bi bi-file-earmark"></i></div>
          <div class="stat-value">{{ total_files }}</div>
          <div class="stat-label">Files Stored</div>
        </div>
        <div class="stat-card">
          <div class="stat-icon"><i class="bi bi-puzzle"></i></div>
          <div class="stat-value">{{ chunk_size_mb }}</div>
          <div class="stat-label">Chunk Size (MB)</div>
        </div>
      </div>
      
      <!-- Tabs -->
      <div class="tabs">
        <div class="tab active" data-tab="upload">Upload</div>
        <div class="tab" data-tab="files">Your Files</div>
      </div>
      
      <!-- Upload Tab -->
      <div class="tab-content active" id="upload-tab">
        <h2>Upload File</h2>
        <div class="upload-form">
          <form method="post" action="/upload" enctype="multipart/form-data" id="upload-form">
            <div class="file-input-container">
              <input type="file" name="file" class="file-input" required>
              <button type="submit" class="btn btn-primary" id="upload-btn">Upload</button>
            </div>
            <small>Files will be split into chunks and stored securely across multiple storage providers.</small>
            <div id="upload-progress" style="display: none; margin-top: 10px;">
              <div style="height: 4px; width: 100%; background-color: #e5e7eb; border-radius: 2px; overflow: hidden;">
                <div id="progress-bar" style="height: 100%; width: 0%; background-color: var(--primary); transition: width 0.3s;"></div>
              </div>
              <small id="progress-text">0%</small>
            </div>
          </form>
        </div>
      </div>
      
      <!-- Files Tab -->
      <div class="tab-content" id="files-tab">
        <h2>Your Files</h2>
        {% if files %}
          <table class="file-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>File ID</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {% for file_id, filename in files %}
                <tr>
                  <td class="file-name-cell">
                    <div class="file-icon">
                      <i class="bi {{ get_file_icon(filename) }}"></i>
                    </div>
                    {{ filename }}
                  </td>
                  <td><small>{{ file_id }}</small></td>
                  <td class="actions">
                    <a href="/download/{{ file_id }}" class="btn btn-primary">Download</a>
                    <a href="/versions/{{ file_id }}" class="btn btn-primary">Versions</a>
                    <form method="post" action="/delete/{{ file_id }}" style="display:inline;">
                      <button type="submit" class="btn btn-danger" onclick="return confirm('Are you sure you want to delete {{ filename }}?');">Delete</button>
                    </form>
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        {% else %}
          <div class="empty-state">
            <p>No files stored yet. Upload your first file above.</p>
          </div>
        {% endif %}
      </div>
    </div>
    
    <div class="footer">
      Amazing Storage System — Secure, Distributed Cloud Storage
    </div>
  </div>
  
  <!-- Chat Widget -->
  <div class="chat-widget collapsed">
    <div class="chat-header">
      <span>Storage Assistant</span>
      <i class="bi bi-chevron-up" id="chat-toggle"></i>
    </div>
    <div class="chat-messages">
      <div class="message bot">
        Hi there! I'm your Storage Assistant. How can I help you with your distributed files today?
      </div>
    </div>
    <div class="chat-input">
      <input type="text" placeholder="Ask something..." id="chat-input-field">
      <button id="send-chat"><i class="bi bi-send"></i></button>
    </div>
  </div>
  
  <script>
    // Chat widget functionality
    document.addEventListener('DOMContentLoaded', function() {
      const chatWidget = document.querySelector('.chat-widget');
      const chatToggle = document.getElementById('chat-toggle');
      const chatInput = document.getElementById('chat-input-field');
      const sendButton = document.getElementById('send-chat');
      const messagesContainer = document.querySelector('.chat-messages');
      
      // Toggle chat open/closed
      chatToggle.addEventListener('click', function() {
        chatWidget.classList.toggle('collapsed');
        chatToggle.classList.toggle('bi-chevron-up');
        chatToggle.classList.toggle('bi-chevron-down');
        if (!chatWidget.classList.contains('collapsed')) {
          chatInput.focus();
        }
      });
      
      // Send message function
      function sendMessage() {
        const message = chatInput.value.trim();
        if (message) {
          // Add user message to chat
          const userMessageElement = document.createElement('div');
          userMessageElement.classList.add('message', 'user');
          userMessageElement.textContent = message;
          messagesContainer.appendChild(userMessageElement);
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
          
          // Clear input
          chatInput.value = '';
          
          // Add loading indicator
          const botMessageElement = document.createElement('div');
          botMessageElement.classList.add('message', 'bot');
          const loader = document.createElement('div');
          loader.classList.add('loader');
          botMessageElement.appendChild(loader);
          messagesContainer.appendChild(botMessageElement);
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
          
          // Get response from backend
          fetch('/chat', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message }),
          })
          .then(response => response.json())
          .then(data => {
            // Replace loading indicator with response
            botMessageElement.textContent = data.response;
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
          })
          .catch(error => {
            botMessageElement.textContent = 'Sorry, I encountered an error. Please try again.';
            console.error('Error:', error);
          });
        }
      }
      
      // Send message on button click
      sendButton.addEventListener('click', sendMessage);
      
      // Send message on Enter key
      chatInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          sendMessage();
        }
      });
      
      // Tab functionality
      const tabs = document.querySelectorAll('.tab');
      tabs.forEach(tab => {
        tab.addEventListener('click', function() {
          // Remove active class from all tabs
          tabs.forEach(t => t.classList.remove('active'));
          
          // Add active class to clicked tab
          this.classList.add('active');
          
          // Hide all tab content
          document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
          });
          
          // Show the corresponding tab content
          const tabId = this.getAttribute('data-tab');
          document.getElementById(tabId + '-tab').classList.add('active');
        });
      });
      
      // Upload form progress simulation
      const uploadForm = document.getElementById('upload-form');
      const progressBar = document.getElementById('progress-bar');
      const progressText = document.getElementById('progress-text');
      const progressContainer = document.getElementById('upload-progress');
      
      uploadForm.addEventListener('submit', function(e) {
        const fileInput = this.querySelector('input[type="file"]');
        if (fileInput.files.length > 0) {
          // Don't simulate progress for very small files
          const fileSize = fileInput.files[0].size;
          if (fileSize > 500000) { // 500KB
            e.preventDefault();
            
            // Show progress
            progressContainer.style.display = 'block';
            let progress = 0;
            
            // Simulate progress
            const interval = setInterval(() => {
              progress += Math.random() * 10;
              if (progress >= 100) {
                progress = 100;
                clearInterval(interval);
                // Submit the form for real after "upload" completes
                setTimeout(() => {
                  uploadForm.submit();
                }, 500);
              }
              progressBar.style.width = progress + '%';
              progressText.textContent = Math.round(progress) + '%';
            }, 300);
          }
        }
      });
    });
  </script>
</body>
</html>
"""

# Add this new template for the version history page
VERSION_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>File Versions - Amazing Storage System</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
  <style>
    /* Reuse the same styles from the main template */
    :root {
      --primary: #4f46e5;
      --primary-hover: #4338ca;
      --danger: #ef4444;
      --danger-hover: #dc2626;
      --success: #10b981;
      --dark: #1f2937;
      --light: #f9fafb;
      --gray: #9ca3af;
      --border: #e5e7eb;
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: 'Inter', sans-serif;
      background-color: #f3f4f6;
      color: #374151;
      line-height: 1.5;
    }
    
    .container {
      max-width: 900px;
      margin: 2rem auto;
      background: white;
      border-radius: 10px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
      overflow: hidden;
    }
    
    .header {
      background-color: var(--primary);
      color: white;
      padding: 1.5rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .header h1 {
      font-weight: 700;
      font-size: 1.75rem;
      margin: 0;
    }
    
    .header-back {
      color: white;
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    
    .content {
      padding: 2rem;
    }
    
    h1, h2 {
      margin: 0;
    }
    
    h2 {
      font-weight: 600;
      font-size: 1.25rem;
      margin-bottom: 1rem;
      color: var(--dark);
    }
    
    .file-info {
      margin-bottom: 2rem;
      padding: 1.5rem;
      background-color: var(--light);
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    
    .file-name {
      font-size: 1.2rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }
    
    .alert {
      padding: 1rem;
      margin-bottom: 1.5rem;
      border-radius: 6px;
    }
    
    .alert-success {
      background-color: rgba(16, 185, 129, 0.1);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.2);
    }
    
    .alert-danger {
      background-color: rgba(239, 68, 68, 0.1);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.2);
    }
    
    .version-table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    
    .version-table th {
      text-align: left;
      padding: 1rem;
      background-color: var(--light);
      font-weight: 600;
      color: var(--dark);
      border-bottom: 1px solid var(--border);
    }
    
    .version-table td {
      padding: 1rem;
      border-bottom: 1px solid var(--border);
    }
    
    .version-table tr:last-child td {
      border-bottom: none;
    }
    
    .version-table tr:hover {
      background-color: rgba(243, 244, 246, 0.5);
    }
    
    .current-version {
      display: inline-block;
      padding: 0.25rem 0.5rem;
      background-color: var(--primary);
      color: white;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 500;
    }
    
    .btn {
      display: inline-block;
      padding: 0.5rem 1rem;
      font-weight: 500;
      text-align: center;
      white-space: nowrap;
      vertical-align: middle;
      cursor: pointer;
      border: none;
      border-radius: 6px;
      font-size: 0.875rem;
      transition: all 0.2s ease;
      text-decoration: none;
    }
    
    .btn-primary {
      background-color: var(--primary);
      color: white;
    }
    
    .btn-primary:hover {
      background-color: var(--primary-hover);
    }
    
    .btn-danger {
      background-color: var(--danger);
      color: white;
    }
    
    .btn-danger:hover {
      background-color: var(--danger-hover);
    }
    
    .footer {
      text-align: center;
      padding: 1rem;
      font-size: 0.875rem;
      color: var(--gray);
      border-top: 1px solid var(--border);
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>File Versions</h1>
      <a href="/" class="header-back"><i class="bi bi-arrow-left"></i> Back to Files</a>
    </div>
    
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}
            <div class="alert alert-{{ category }}">{{ message }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      
      <div class="file-info">
        <div class="file-name">{{ filename }}</div>
        <div class="file-id">File ID: {{ file_id }}</div>
      </div>
      
      <div class="version-actions">
        <a href="/update/{{ file_id }}" class="btn btn-primary"><i class="bi bi-upload"></i> Upload New Version</a>
      </div>
      
      <h2>Available Versions</h2>
      
      {% if versions %}
        <table class="version-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Date</th>
              <th>Notes</th>
              <th>Chunks</th>
              <th>Encryption</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {% for version in versions %}
              <tr>
                <td>
                  {% if version.is_current %}
                    <span class="current-version">Current</span>
                  {% else %}
                    <span>{{ loop.index }}</span>
                  {% endif %}
                </td>
                <td>{{ version.timestamp }}</td>
                <td>{{ version.notes }}</td>
                <td>{{ version.chunk_count }}</td>
                <td>{{ version.encryption }}</td>
                <td>
                  {% if not version.is_current %}
                    <form method="post" action="/restore/{{ file_id }}/{{ version.version_id }}" style="display:inline;">
                      <button type="submit" class="btn btn-primary" onclick="return confirm('Are you sure you want to restore this version?');">Restore</button>
                    </form>
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      {% else %}
        <div class="empty-state">
          <p>No versions available for this file.</p>
        </div>
      {% endif %}
    </div>
    
    <div class="footer">
      Amazing Storage System — Secure, Distributed Cloud Storage
    </div>
  </div>
</body>
</html>
"""

# Add this new template for updating files
UPDATE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Update File - Amazing Storage System</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
  <style>
    /* Reuse the same styles from the main template */
    :root {
      --primary: #4f46e5;
      --primary-hover: #4338ca;
      --danger: #ef4444;
      --danger-hover: #dc2626;
      --success: #10b981;
      --dark: #1f2937;
      --light: #f9fafb;
      --gray: #9ca3af;
      --border: #e5e7eb;
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: 'Inter', sans-serif;
      background-color: #f3f4f6;
      color: #374151;
      line-height: 1.5;
    }
    
    .container {
      max-width: 900px;
      margin: 2rem auto;
      background: white;
      border-radius: 10px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
      overflow: hidden;
    }
    
    .header {
      background-color: var(--primary);
      color: white;
      padding: 1.5rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .header h1 {
      font-weight: 700;
      font-size: 1.75rem;
      margin: 0;
    }
    
    .header-back {
      color: white;
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    
    .content {
      padding: 2rem;
    }
    
    h1, h2 {
      margin: 0;
    }
    
    h2 {
      font-weight: 600;
      font-size: 1.25rem;
      margin-bottom: 1rem;
      color: var(--dark);
    }
    
    .file-info {
      margin-bottom: 2rem;
      padding: 1.5rem;
      background-color: var(--light);
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    
    .file-name {
      font-size: 1.2rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }
    
    .alert {
      padding: 1rem;
      margin-bottom: 1.5rem;
      border-radius: 6px;
    }
    
    .alert-success {
      background-color: rgba(16, 185, 129, 0.1);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.2);
    }
    
    .alert-danger {
      background-color: rgba(239, 68, 68, 0.1);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.2);
    }
    
    .upload-form {
      background-color: var(--light);
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 2rem;
      border: 1px solid var(--border);
    }
    
    .form-group {
      margin-bottom: 1rem;
    }
    
    .form-group label {
      display: block;
      margin-bottom: 0.5rem;
      font-weight: 500;
    }
    
    .form-group input[type="file"] {
      width: 100%;
      border: 1px solid var(--border);
      padding: 0.5rem;
      border-radius: 6px;
    }
    
    .form-group textarea {
      width: 100%;
      border: 1px solid var(--border);
      padding: 0.5rem;
      border-radius: 6px;
      min-height: 100px;
      font-family: inherit;
    }
    
    .btn {
      display: inline-block;
      padding: 0.5rem 1rem;
      font-weight: 500;
      text-align: center;
      white-space: nowrap;
      vertical-align: middle;
      cursor: pointer;
      border: none;
      border-radius: 6px;
      font-size: 0.875rem;
      transition: all 0.2s ease;
      text-decoration: none;
    }
    
    .btn-primary {
      background-color: var(--primary);
      color: white;
    }
    
    .btn-primary:hover {
      background-color: var(--primary-hover);
    }
    
    .footer {
      text-align: center;
      padding: 1rem;
      font-size: 0.875rem;
      color: var(--gray);
      border-top: 1px solid var(--border);
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Update File</h1>
      <a href="/versions/{{ file_id }}" class="header-back"><i class="bi bi-arrow-left"></i> Back to Versions</a>
    </div>
    
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}
            <div class="alert alert-{{ category }}">{{ message }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      
      <div class="file-info">
        <div class="file-name">{{ filename }}</div>
        <div class="file-id">File ID: {{ file_id }}</div>
      </div>
      
      <h2>Upload New Version</h2>
      
      <div class="upload-form">
        <form method="post" action="/update/{{ file_id }}" enctype="multipart/form-data">
          <div class="form-group">
            <label for="file">Select File</label>
            <input type="file" name="file" id="file" required>
          </div>
          
          <div class="form-group">
            <label for="version_notes">Version Notes</label>
            <textarea name="version_notes" id="version_notes" placeholder="Describe what changed in this version..."></textarea>
          </div>
          
          <button type="submit" class="btn btn-primary">Upload New Version</button>
        </form>
      </div>
    </div>
    
    <div class="footer">
      Amazing Storage System — Secure, Distributed Cloud Storage
    </div>
  </div>
</body>
</html>
"""

# --- Routes ---

@app.route('/', methods=['GET'])
def index():
    """Displays the main page with the file list and upload form."""
    try:
        stored_files = chunk_manager.list_files()
        stored_files.sort(key=lambda item: item[1].lower())
        
        total_providers = len(chunk_manager.providers)
        total_files = len(stored_files)
        chunk_size_mb = app_config.chunk_size / (1024 * 1024)
        
    except Exception as e:
        app.logger.error(f"Error listing files: {e}")
        flash(f"Error listing files: {e}", "danger")
        stored_files = []
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
    
    return render_template_string(
        HTML_TEMPLATE, 
        files=stored_files,
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
        # Save temporarily locally before chunking
        # Secure filename handling is important in production
        from werkzeug.utils import secure_filename
        filename = file.filename # Use original for now
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        
        try:
            file.save(temp_path)
            app.logger.info(f"File temporarily saved to: {temp_path}")
            
            # Upload using ChunkManager
            file_id = chunk_manager.upload_file(temp_path, original_filename=filename)
            
            # Clean up temporary file immediately after successful upload starts
            os.remove(temp_path) 
            app.logger.info(f"Temporary file removed: {temp_path}")

            if file_id:
                flash(f"File '{filename}' uploaded successfully (ID: {file_id})", "success")
                return jsonify({"message": f"File '{filename}' uploaded successfully", "file_id": file_id}), 201
            else:
                flash(f"Failed to upload file '{filename}'", "danger")
                return jsonify({"error": f"Failed to upload file '{filename}'. Check logs."}), 500
        
        except Exception as e:
             app.logger.error(f"Error during upload process for {filename}: {e}")
             # Ensure temporary file is cleaned up even on error
             if os.path.exists(temp_path):
                  try:
                       os.remove(temp_path)
                       app.logger.info(f"Temporary file removed after error: {temp_path}")
                  except OSError as rm_err:
                       app.logger.error(f"Error removing temp file {temp_path} after error: {rm_err}")
             flash(f"An unexpected error occurred during upload: {e}", "danger")
             return jsonify({"error": f"An internal error occurred during upload."}), 500
    
    return jsonify({"error": "File processing failed."}), 500

@app.route('/download/<file_id>', methods=['GET'])
def download_file_route(file_id):
    """Handles file downloads."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        abort(404, description="File not found")

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
async def chat():
    """Handle chat messages using the AI chatbot."""
    try:
        message = request.json.get('message', '')
        if not message:
            return jsonify({"response": "Please send a message to chat."}), 400
            
        if not chatbot_client.is_enabled():
            return jsonify({"response": "Sorry, the chatbot is not available at the moment."}), 200
            
        # Create system context about the storage system
        system_context = (
            "You are a helpful assistant for the Amazing Storage System, which is a distributed file storage "
            "application that splits files into chunks and stores them across multiple cloud storage providers "
            "for redundancy. The system is currently connected to multiple Google Drive and Dropbox accounts. "
            "You can help users understand how their files are stored, the benefits of distributed storage, "
            "and general file management questions."
        )
        
        full_prompt = f"{system_context}\n\nUser question: {message}"
        
        # Get response from the chatbot - directly use the async function
        response = await chatbot_client.get_response(full_prompt)
        
        return jsonify({"response": response}), 200
    
    except Exception as e:
        app.logger.error(f"Error in chat endpoint: {e}")
        return jsonify({"response": f"Sorry, an error occurred: {str(e)}"}), 500

@app.route('/versions/<file_id>', methods=['GET'])
def view_versions(file_id):
    """Display version history for a file."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        abort(404, description="File not found")
    
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
            'encryption': 'Enabled' if version.encryption_enabled else 'Disabled'
        })
    
    return render_template_string(VERSION_TEMPLATE, 
                                 file_id=file_id, 
                                 filename=manifest.original_filename,
                                 versions=formatted_versions)

@app.route('/restore/<file_id>/<version_id>', methods=['POST'])
def restore_version(file_id, version_id):
    """Restore a previous version of a file."""
    manifest = metadata_manager.load_manifest(file_id)
    if not manifest:
        abort(404, description="File not found")
    
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
    return render_template_string(UPDATE_TEMPLATE, 
                                 file_id=file_id, 
                                 filename=manifest.original_filename)

def run_app():
    print(f"Flask development server starting on http://{app_config.web_interface_host}:{app_config.web_interface_port}")
    app.run(host=app_config.web_interface_host, port=app_config.web_interface_port, debug=True)

if __name__ == '__main__':
     run_app()
