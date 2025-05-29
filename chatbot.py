from flask import Blueprint, request, jsonify
import requests

chatbot_bp = Blueprint('chatbot', __name__)

@chatbot_bp.route('/api/chatbot', methods=['POST'])
def chatbot_api():
    user_message = request.json.get('message', '')
    
    # Use HuggingFace Inference API (free tier)
    API_URL = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill"
    headers = {"Authorization": "Bearer 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"}  # Free API key with limitations
    
    def query(payload):
        response = requests.post(API_URL, headers=headers, json=payload)
        return response.json()
    
    # Get response from model
    try:
        output = query({
            "inputs": {
                "past_user_inputs": ["Hi"],
                "generated_responses": ["Hello, how can I help you?"],
                "text": user_message
            },
        })
        
        # Extract the response
        bot_response = output.get('generated_text', 'Sorry, I could not process your request.')
        
        # Add crisis management context
        if "incident" in user_message.lower() or "report" in user_message.lower():
            bot_response += " If you need to report an incident, use the 'Report Incident' button in the navigation menu."
        elif "emergency" in user_message.lower():
            bot_response = "For immediate emergencies, please call emergency services directly. This system is for reporting and tracking incidents."
        
        return jsonify({"response": bot_response})
    except Exception as e:
        return jsonify({"response": "I'm having trouble connecting right now. Please try again later."})