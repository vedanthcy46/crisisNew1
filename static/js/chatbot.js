document.addEventListener('DOMContentLoaded', function() {
  const chatButton = document.getElementById('chat-button');
  const chatMessages = document.getElementById('chat-messages');
  const closeChat = document.getElementById('close-chat');
  const userInput = document.getElementById('user-input');
  const sendMessage = document.getElementById('send-message');
  const messagesArea = document.getElementById('messages-area');
  
  // Toggle chat panel
  chatButton.addEventListener('click', function() {
    chatMessages.style.display = chatMessages.style.display === 'flex' ? 'none' : 'flex';
  });
  
  closeChat.addEventListener('click', function() {
    chatMessages.style.display = 'none';
  });
  
  // Send message function
  function sendUserMessage() {
    const message = userInput.value.trim();
    if (message) {
      // Add user message
      const userMessageDiv = document.createElement('div');
      userMessageDiv.className = 'user-message';
      userMessageDiv.textContent = message;
      messagesArea.appendChild(userMessageDiv);
      
      // Clear input
      userInput.value = '';
      
      // Scroll to bottom
      messagesArea.scrollTop = messagesArea.scrollHeight;
      
      // Get bot response
      getBotResponse(message);
    }
  }
  
  // Get bot response from API
  function getBotResponse(userMessage) {
    // Show typing indicator
    const typingDiv = document.createElement('div');
    typingDiv.className = 'bot-message typing';
    typingDiv.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    messagesArea.appendChild(typingDiv);
    
    // Scroll to bottom
    messagesArea.scrollTop = messagesArea.scrollHeight;
    
    // Call the API
    fetch('/api/chatbot', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: userMessage }),
    })
    .then(response => response.json())
    .then(data => {
      // Remove typing indicator
      messagesArea.removeChild(typingDiv);
      
      // Add bot response
      const botMessageDiv = document.createElement('div');
      botMessageDiv.className = 'bot-message';
      botMessageDiv.textContent = data.response;
      messagesArea.appendChild(botMessageDiv);
      
      // Scroll to bottom
      messagesArea.scrollTop = messagesArea.scrollHeight;
    })
    .catch(error => {
      // Remove typing indicator
      messagesArea.removeChild(typingDiv);
      
      // Show error message
      const botMessageDiv = document.createElement('div');
      botMessageDiv.className = 'bot-message';
      botMessageDiv.textContent = "Sorry, I'm having trouble connecting right now. Please try again later.";
      messagesArea.appendChild(botMessageDiv);
      
      // Scroll to bottom
      messagesArea.scrollTop = messagesArea.scrollHeight;
    });
  }
  
  // Event listeners for sending messages
  sendMessage.addEventListener('click', sendUserMessage);
  userInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      sendUserMessage();
    }
  });
});