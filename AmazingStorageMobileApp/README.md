# Amazing Storage Mobile App

A React Native mobile app for the Amazing Storage System.

## Features

- View all your stored files in one place
- Upload new files to your distributed storage system
- Download files to your device
- Delete files you no longer need
- Share files with others through links
- User authentication

## Setup Instructions

### Prerequisites

- Node.js (v16 or higher)
- npm or yarn
- Expo CLI (`npm install -g expo-cli`)

### Installation

1. Clone this repository
2. Navigate to the AmazingStorageMobileApp folder:
   ```
   cd AmazingStorageMobileApp
   ```
3. Install dependencies:
   ```
   npm install
   ```
   or
   ```
   yarn install
   ```

### Configuration

Before running the app, you need to configure it to connect to your Amazing Storage server:

1. Open `App.js`
2. Find the `API_BASE_URL` constant near the top of the file
3. Replace it with your server's IP address and port:
   ```javascript
   const API_BASE_URL = 'http://your-server-ip:5000';
   ```

### Running the App

1. Start the development server:
   ```
   npm start
   ```
   or
   ```
   yarn start
   ```

2. Use the Expo Go app on your phone to scan the QR code and run the app, or:
   - Press `a` to run on an Android emulator
   - Press `i` to run on an iOS simulator (Mac only)

## Implementing File Upload

To implement actual file uploads, you'll need to:

1. Import and use the document picker:
   ```javascript
   import * as DocumentPicker from 'expo-document-picker';
   ```

2. Add a function to pick and upload a file:
   ```javascript
   const pickDocument = async () => {
     try {
       const result = await DocumentPicker.getDocumentAsync({
         type: '*/*',
         copyToCacheDirectory: true,
       });
       
       if (result.canceled) {
         return;
       }
       
       // Upload the file using FormData
       const formData = new FormData();
       formData.append('file', {
         uri: result.assets[0].uri,
         name: result.assets[0].name,
         type: 'application/octet-stream',
       });
       
       const response = await axios.post(`${API_BASE_URL}/api/upload`, formData, {
         headers: {
           'Content-Type': 'multipart/form-data',
         },
       });
       
       if (response.status === 201) {
         Alert.alert('Success', 'File uploaded successfully');
         fetchFiles(); // Refresh file list
       }
     } catch (error) {
       Alert.alert('Error', `Failed to upload file: ${error.message}`);
     }
   };
   ```

## Connecting to Your Project's API

Review how the app connects to your Flask API:

1. File listing: `GET /api/files`
2. File upload: `POST /api/upload` (with FormData)
3. File download: `GET /api/download/{file_id}`
4. File deletion: `DELETE /api/delete/{file_id}`

Ensure your server has these endpoints implemented correctly.

## For Faculty Demonstration

When demonstrating to faculty:

1. Have your server running on a local network where both your mobile device and server are connected
2. Make sure to update `API_BASE_URL` with the correct IP address of your server
3. Prepare test files of different types to show the upload/download functionality
4. Highlight how the app connects to your distributed storage system
5. Show the security aspects of the application 