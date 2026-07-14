const chatForm = document.getElementById('chat-form');
const chatContainer = document.getElementById('chat-container');
const userInput = document.getElementById('user-input');
const API_BASE_URL = 'https://unheaded-braydon-semipronely.ngrok-free.dev';

function addMessage(text, sender) {
    const div = document.createElement('div');
    div.classList.add('message', `${sender}-message`);

    if (sender === 'ai') {
        const rawHtml = marked.parse(text);
        div.innerHTML = DOMPurify.sanitize(rawHtml);
    } else {
        div.innerText = text;
    }

    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function showTypingIndicator() {
    const div = document.createElement('div');
    div.classList.add('typing-indicator');
    div.id = 'typing';
    div.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function removeTypingIndicator() {
    const typingElement = document.getElementById('typing');
    if (typingElement) {
        typingElement.remove();
    }
}

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const message = userInput.value.trim();
    if (!message) return;

    addMessage(message, 'user');
    userInput.value = '';
    showTypingIndicator();

    try {
        // Goes through the Node backend (which validates input and talks to the RAG engine)
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
    },
    body: JSON.stringify({ message }),
});

        const result = await response.json();
        removeTypingIndicator();

        if (response.ok && result.success && result.data?.answer) {
            addMessage(result.data.answer, 'ai');
        } else {
            addMessage(result.error || "I couldn't process that. Please try again.", 'ai');
        }

    } catch (error) {
        removeTypingIndicator();
        addMessage("Connection lost. Is the server running? 🔌", 'ai');
    }
});
