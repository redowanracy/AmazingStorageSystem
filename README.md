# Amazing Storage System

A distributed file storage solution that spreads your data across multiple cloud storage providers for maximum redundancy and reliability.

## Features

- **Distributed Storage**: Files are split into chunks and stored across multiple cloud providers (Google Drive, Dropbox)
- **Redundancy & Security**: Data loss from a single provider doesn't compromise your files
- **Modern Web Interface**: Easy to use file management with upload/download capabilities
- **AI Assistant**: Built-in chatbot to help with questions about your storage system
- **Provider Agnostic**: Works with multiple cloud storage providers simultaneously
- **Visual Dashboard**: See storage statistics and file information at a glance
- **Progress Tracking**: Upload progress visualization for large files

## Getting Started

1. Clone the repository:
   ```
   git clone [repository-url]
   cd AmazingStorageSystem
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Configure your storage providers:
   - Edit `config.json` to add your storage provider credentials
   - You need at least one valid provider account (Google Drive or Dropbox)

4. Run the application:
   ```
   python main.py
   ```

5. Access the web interface:
   - Open your browser and navigate to `http://127.0.0.1:5000`

## How It Works

The Amazing Storage System takes your files and:

1. Splits them into manageable chunks
2. Distributes these chunks across multiple cloud storage providers
3. Maintains a local manifest of where each chunk is stored
4. Reassembles files on download by retrieving all chunks

This approach provides several benefits:
- **Redundancy**: If one provider has issues, your data remains accessible
- **Security**: Your complete file isn't stored on any single service
- **Storage Optimization**: Makes better use of free tiers across multiple providers

## Configuration

The system is configured through the `config.json` file:

```json
{
  "buckets": [
    {
      "type": "google",
      "credentials": "google_acc0.json",
      "folder_id": "your-folder-id"
    },
    {
      "type": "dropbox",
      "credentials": "dropbox_acc0.txt",
      "folder_path": "/AmazingStorage0"
    }
  ],
  "chunk_size": 5242880,
  "encryption_enabled": false,
  "web_interface_host": "127.0.0.1",
  "web_interface_port": 5000,
  "chatbot_provider": "gemini",
  "chatbot_api_key": "your-api-key"
}
```

## AI Assistant

The system includes an AI chatbot that can:
- Answer questions about how your files are stored
- Explain the benefits of distributed storage
- Provide general file management guidance
- Assist with understanding system features

## License

MIT License 