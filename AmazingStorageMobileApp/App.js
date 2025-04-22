import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, FlatList, ActivityIndicator, SafeAreaView, StatusBar, TouchableOpacity, Alert, Modal, TextInput, Button } from 'react-native';
import axios from 'axios'; // Import axios
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system';
import * as SecureStore from 'expo-secure-store';

// --- IMPORTANT ---
// Replace with your computer's actual local IP address if running on a physical device
// Find your IP: 'ipconfig' (Windows) or 'ifconfig'/'ip addr' (Mac/Linux)
// If using Android Emulator, use 10.0.2.2
// If using iOS Simulator, 127.0.0.1 or localhost should work
const API_BASE_URL = 'http://192.168.0.104:5000'; // <--- CHANGE THIS IP ADDRESS
// ---------------

export default function App() {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeScreen, setActiveScreen] = useState('files'); // 'files', 'upload', 'account'
  const [loginVisible, setLoginVisible] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileOptionsVisible, setFileOptionsVisible] = useState(false);

  useEffect(() => {
    fetchFiles();
  }, []); // Empty dependency array means run once on mount

  const fetchFiles = async () => {
    setLoading(true);
    setError(null);
    try {
      console.log(`Fetching files from: ${API_BASE_URL}/api/files`);
      const response = await axios.get(`${API_BASE_URL}/api/files`);
      console.log("API Response:", response.data);
      if (response.data && Array.isArray(response.data.files)) {
        setFiles(response.data.files);
      } else {
        console.error("Unexpected response format:", response.data);
        setError("Received unexpected data format from server.");
      }
    } catch (err) {
      console.error("Fetch error:", err);
      let errorMessage = "Failed to fetch files.";
      if (err.response) {
        // Server responded with a status code outside 2xx range
        errorMessage += ` Server Error: ${err.response.status} - ${JSON.stringify(err.response.data)}`;
      } else if (err.request) {
        // Request was made but no response received (network issue?)
        errorMessage += " No response from server. Is it running? Is the IP correct?";
      } else {
        // Something else happened in setting up the request
        errorMessage += ` Error: ${err.message}`;
      }
       setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    if (!username || !password) {
      Alert.alert('Error', 'Please enter both username and password');
      return;
    }

    try {
      setLoading(true);
      // Integrate with your actual login API
      // For demo, we'll simulate successful login
      setTimeout(() => {
        setIsLoggedIn(true);
        setLoginVisible(false);
        setLoading(false);
        Alert.alert('Success', 'You are now logged in');
      }, 1000);
      
      // Actual API call would look like:
      // const response = await axios.post(`${API_BASE_URL}/login`, {
      //   username,
      //   password,
      // });
      // setIsLoggedIn(true);
      // setLoginVisible(false);
    } catch (err) {
      setLoading(false);
      Alert.alert('Login Failed', err.message || 'Check your credentials and try again');
    }
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    setUsername('');
    setPassword('');
    Alert.alert('Success', 'You have been logged out');
  };

  const handleFilePress = (file) => {
    setSelectedFile(file);
    setFileOptionsVisible(true);
  };

  const handleUpload = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: true,
      });
      
      if (result.canceled) {
        return;
      }
      
      setLoading(true);
      
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
      
      setLoading(false);
      
      if (response.status === 201) {
        Alert.alert('Success', 'File uploaded successfully');
        fetchFiles(); // Refresh file list
        setActiveScreen('files'); // Navigate back to files screen
      }
    } catch (error) {
      setLoading(false);
      Alert.alert('Error', `Failed to upload file: ${error.message}`);
    }
  };

  const handleDownload = async () => {
    try {
      setFileOptionsVisible(false);
      setLoading(true);
      
      // Get the download URL
      const downloadUrl = `${API_BASE_URL}/api/download/${selectedFile.id}`;
      
      // Define where to save the file
      const fileUri = FileSystem.documentDirectory + selectedFile.name;
      
      // Download the file
      const downloadResult = await FileSystem.downloadAsync(
        downloadUrl,
        fileUri
      );
      
      setLoading(false);
      
      if (downloadResult.status === 200) {
        Alert.alert(
          'Download Complete',
          `File saved to: ${fileUri}`,
          [
            {
              text: 'OK',
              onPress: () => console.log('OK Pressed'),
            },
          ]
        );
      } else {
        Alert.alert('Error', 'Failed to download file');
      }
    } catch (error) {
      setLoading(false);
      Alert.alert('Error', `Failed to download file: ${error.message}`);
    }
  };

  const handleDelete = async () => {
    try {
      Alert.alert(
        'Confirm Delete',
        `Are you sure you want to delete '${selectedFile.name}'?`,
        [
          {
            text: 'Cancel',
            style: 'cancel',
          },
          {
            text: 'Delete',
            onPress: async () => {
              // Implement actual deletion using your API
              // const response = await axios.delete(`${API_BASE_URL}/api/delete/${selectedFile.id}`);
              Alert.alert('Success', `File '${selectedFile.name}' deleted`);
              setFileOptionsVisible(false);
              fetchFiles(); // Refresh the file list
            },
            style: 'destructive',
          },
        ]
      );
    } catch (error) {
      Alert.alert('Error', `Failed to delete file: ${error.message}`);
    }
  };

  const handleShare = () => {
    Alert.alert('Share', `Generate sharing link for '${selectedFile.name}'`);
    // Implement sharing functionality
    setFileOptionsVisible(false);
  };

  const renderFileItem = ({ item }) => (
    <TouchableOpacity 
      style={styles.item} 
      onPress={() => handleFilePress(item)}
    >
      <Ionicons 
        name={item.name.endsWith('.pdf') ? 'document-text' : 
              item.name.endsWith('.jpg') || item.name.endsWith('.png') ? 'image' : 
              'document'} 
        size={24} 
        color="#4285F4"
        style={styles.fileIcon} 
      />
      <View style={styles.fileInfo}>
        <Text style={styles.fileName}>{item.name}</Text>
        <Text style={styles.fileSize}>{item.size ? `${(item.size / 1024 / 1024).toFixed(2)} MB` : 'Unknown size'}</Text>
      </View>
    </TouchableOpacity>
  );

  const renderFileScreen = () => (
    <View style={styles.screenContainer}>
      <Text style={styles.title}>Your Files</Text>
      {loading && <ActivityIndicator size="large" color="#4285F4" />}
      {error && <Text style={styles.errorText}>{error}</Text>}
      {!loading && !error && (
        <FlatList
          data={files}
          renderItem={renderFileItem}
          keyExtractor={item => item.id}
          ListEmptyComponent={<Text style={styles.emptyText}>No files found.</Text>}
        />
      )}
    </View>
  );

  const renderUploadScreen = () => (
    <View style={styles.screenContainer}>
      <Text style={styles.title}>Upload Files</Text>
      <View style={styles.uploadContainer}>
        <Ionicons name="cloud-upload" size={80} color="#4285F4" />
        <Text style={styles.uploadText}>Select files to upload</Text>
        <TouchableOpacity style={styles.button} onPress={handleUpload}>
          <Text style={styles.buttonText}>Choose Files</Text>
        </TouchableOpacity>
        <Text style={styles.uploadNote}>
          Files will be uploaded to your Amazing Storage account and
          distributed across multiple cloud storage providers.
        </Text>
      </View>
    </View>
  );

  const renderAccountScreen = () => (
    <View style={styles.screenContainer}>
      <Text style={styles.title}>Account</Text>
      {isLoggedIn ? (
        <View style={styles.accountContainer}>
          <Ionicons name="person-circle" size={100} color="#4285F4" />
          <Text style={styles.accountName}>{username || 'Demo User'}</Text>
          <Text style={styles.accountDetail}>Storage Used: 122 MB / 1 GB</Text>
          <Text style={styles.accountDetail}>Files Stored: {files.length}</Text>
          <TouchableOpacity style={styles.button} onPress={handleLogout}>
            <Text style={styles.buttonText}>Logout</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.accountContainer}>
          <Ionicons name="person-outline" size={100} color="#757575" />
          <Text style={styles.loginPrompt}>Please login to see your account details</Text>
          <TouchableOpacity style={styles.button} onPress={() => setLoginVisible(true)}>
            <Text style={styles.buttonText}>Login</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />
      
      {/* Main Content Area */}
      {activeScreen === 'files' && renderFileScreen()}
      {activeScreen === 'upload' && renderUploadScreen()}
      {activeScreen === 'account' && renderAccountScreen()}
      
      {/* File Options Modal */}
      <Modal
        visible={fileOptionsVisible}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setFileOptionsVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContainer}>
            <Text style={styles.modalTitle}>{selectedFile?.name}</Text>
            <TouchableOpacity style={styles.modalOption} onPress={handleDownload}>
              <Ionicons name="download" size={24} color="#4285F4" />
              <Text style={styles.modalOptionText}>Download</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.modalOption} onPress={handleShare}>
              <Ionicons name="share" size={24} color="#4285F4" />
              <Text style={styles.modalOptionText}>Share</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.modalOption} onPress={handleDelete}>
              <Ionicons name="trash" size={24} color="#F44336" />
              <Text style={[styles.modalOptionText, {color: '#F44336'}]}>Delete</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.closeButton} onPress={() => setFileOptionsVisible(false)}>
              <Text style={styles.closeButtonText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
      
      {/* Login Modal */}
      <Modal
        visible={loginVisible}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setLoginVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContainer}>
            <Text style={styles.modalTitle}>Login</Text>
            <TextInput
              style={styles.input}
              placeholder="Username"
              value={username}
              onChangeText={setUsername}
            />
            <TextInput
              style={styles.input}
              placeholder="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
            <TouchableOpacity style={styles.button} onPress={handleLogin}>
              <Text style={styles.buttonText}>Login</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.closeButton} onPress={() => setLoginVisible(false)}>
              <Text style={styles.closeButtonText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
      
      {/* Bottom Navigation */}
      <View style={styles.bottomNav}>
        <TouchableOpacity 
          style={styles.navItem} 
          onPress={() => setActiveScreen('files')}
        >
          <Ionicons 
            name={activeScreen === 'files' ? "folder" : "folder-outline"} 
            size={24} 
            color={activeScreen === 'files' ? "#4285F4" : "#757575"} 
          />
          <Text 
            style={[
              styles.navText, 
              activeScreen === 'files' && styles.activeNavText
            ]}
          >
            Files
          </Text>
        </TouchableOpacity>
        
        <TouchableOpacity 
          style={styles.navItem} 
          onPress={() => setActiveScreen('upload')}
        >
          <Ionicons 
            name={activeScreen === 'upload' ? "cloud-upload" : "cloud-upload-outline"} 
            size={24} 
            color={activeScreen === 'upload' ? "#4285F4" : "#757575"} 
          />
          <Text 
            style={[
              styles.navText, 
              activeScreen === 'upload' && styles.activeNavText
            ]}
          >
            Upload
          </Text>
        </TouchableOpacity>
        
        <TouchableOpacity 
          style={styles.navItem} 
          onPress={() => setActiveScreen('account')}
        >
          <Ionicons 
            name={activeScreen === 'account' ? "person" : "person-outline"} 
            size={24} 
            color={activeScreen === 'account' ? "#4285F4" : "#757575"} 
          />
          <Text 
            style={[
              styles.navText, 
              activeScreen === 'account' && styles.activeNavText
            ]}
          >
            Account
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    marginTop: StatusBar.currentHeight || 0,
  },
  screenContainer: {
    flex: 1,
    paddingBottom: 60, // Space for bottom nav
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginVertical: 15,
    textAlign: 'center',
    color: '#333',
  },
  item: {
    backgroundColor: '#ffffff',
    flexDirection: 'row',
    alignItems: 'center',
    padding: 15,
    marginVertical: 5,
    marginHorizontal: 10,
    borderRadius: 10,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 1.5,
    elevation: 2,
  },
  fileIcon: {
    marginRight: 15,
  },
  fileInfo: {
    flex: 1,
  },
  fileName: {
    fontSize: 16,
    fontWeight: '500',
    color: '#333',
  },
  fileSize: {
    fontSize: 12,
    color: '#888',
    marginTop: 5,
  },
  fileId: {
    fontSize: 12,
    color: '#888',
    marginTop: 3,
  },
  errorText: {
    color: 'red',
    textAlign: 'center',
    margin: 15,
    fontSize: 14,
  },
  emptyText: {
    textAlign: 'center',
    marginTop: 30,
    fontSize: 16,
    color: '#666',
  },
  bottomNav: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: 60,
    backgroundColor: '#ffffff',
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
  },
  navItem: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
  },
  navText: {
    fontSize: 12,
    color: '#757575',
    marginTop: 3,
  },
  activeNavText: {
    color: '#4285F4',
    fontWeight: '500',
  },
  uploadContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  uploadText: {
    fontSize: 18,
    marginVertical: 20,
    color: '#333',
  },
  uploadNote: {
    fontSize: 12,
    color: '#757575',
    textAlign: 'center',
    marginTop: 20,
    paddingHorizontal: 20,
  },
  accountContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  accountName: {
    fontSize: 24,
    fontWeight: 'bold',
    marginTop: 15,
    color: '#333',
  },
  accountDetail: {
    fontSize: 16,
    color: '#666',
    marginTop: 10,
  },
  loginPrompt: {
    fontSize: 16,
    color: '#666',
    marginVertical: 20,
    textAlign: 'center',
  },
  button: {
    backgroundColor: '#4285F4',
    paddingVertical: 12,
    paddingHorizontal: 30,
    borderRadius: 25,
    marginTop: 20,
  },
  buttonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '500',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContainer: {
    width: '80%',
    backgroundColor: 'white',
    borderRadius: 10,
    padding: 20,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 5,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 20,
    color: '#333',
    textAlign: 'center',
  },
  modalOption: {
    flexDirection: 'row',
    alignItems: 'center',
    width: '100%',
    padding: 15,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  modalOptionText: {
    fontSize: 16,
    marginLeft: 15,
    color: '#333',
  },
  closeButton: {
    marginTop: 15,
    padding: 10,
  },
  closeButtonText: {
    color: '#757575',
    fontSize: 16,
  },
  input: {
    width: '100%',
    height: 50,
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 5,
    marginBottom: 15,
    paddingHorizontal: 15,
    fontSize: 16,
  },
});
