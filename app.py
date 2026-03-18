#!/usr/bin/env python3
"""
V-Scale Analyzer Backend
Analyzes attractiveness using the V-scale system

Webhook notification via Discord - no polling needed!
Auto-analysis using Llama 3.2 Vision (essentially free!)
"""

import os
import base64
import json
import requests
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PENDING_FILE = 'pending.json'
RESPONSES_DIR = 'responses'
os.makedirs(RESPONSES_DIR, exist_ok=True)

# OpenRouter API for auto-analysis (Llama 3.2 Vision - essentially free!)
# IMPORTANT: Set OPENROUTER_API_KEY as an environment variable in production!
# Do NOT hardcode keys in production code!
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions'

# Raise error if no key configured (for production safety)
if not OPENROUTER_API_KEY:
    print("WARNING: No OPENROUTER_API_KEY set! Set it as an environment variable.")

# Discord webhook - set via environment variable or edit here
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')

def get_pending():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, 'r') as f:
            return json.load(f)
    return []

def add_pending(filename):
    pending = get_pending()
    pending.append({
        'filename': filename,
        'timestamp': datetime.now().isoformat(),
        'status': 'pending'
    })
    with open(PENDING_FILE, 'w') as f:
        json.dump(pending, f)

def update_pending_status(filename, status):
    """Update the status of a pending file"""
    pending = get_pending()
    for item in pending:
        if item['filename'] == filename:
            item['status'] = status
            break
    with open(PENDING_FILE, 'w') as f:
        json.dump(pending, f)

def save_response(filename, response_data):
    response_file = os.path.join(RESPONSES_DIR, f'{filename}.json')
    with open(response_file, 'w') as f:
        json.dump(response_data, f)

def get_response(filename):
    response_file = os.path.join(RESPONSES_DIR, f'{filename}.json')
    if os.path.exists(response_file):
        with open(response_file, 'r') as f:
            return json.load(f)
    return None

def send_discord_notification(filename, image_url=None):
    """Send notification to Discord when new image uploaded"""
    if not DISCORD_WEBHOOK_URL:
        return False, "No Discord webhook URL configured"
    
    # Create embed message
    embed = {
        "title": "📸 New V-Scale Image Uploaded!",
        "description": f"**File:** {filename}\n\n🤖 Auto-analysis in progress...",
        "color": 5813263,  # Greenish
        "footer": {"text": "V-Scale Analyzer"},
        "timestamp": datetime.now().isoformat()
    }
    
    payload = {
        "embeds": [embed],
        "username": "V-Scale Analyzer"
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204:
            return True, "Notification sent!"
        else:
            return False, f"Discord error: {response.status_code}"
    except Exception as e:
        return False, str(e)

def analyze_with_llama_vision(filepath):
    """Analyze image using Llama 3.2 Vision via OpenRouter - essentially free!"""
    try:
        # Read and encode image
        with open(filepath, 'rb') as f:
            image_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # Build prompt for V-scale analysis - detailed format to ensure proper JSON
        prompt = """Analyze this person's attractiveness. Return ONLY this JSON format, no other text:

{
  "physical_attributes": {
    "facial_structure": {"score": 8, "reason": "balanced and proportional features"},
    "symmetry": {"score": 8, "reason": "harmonious facial proportions"},
    "bone_structure": {"score": 8, "reason": "well-defined cheekbones and jawline"},
    "skin_quality": {"score": 9, "reason": "smooth and radiant complexion"},
    "eyes": {"score": 9, "reason": "bright and expressive eyes"},
    "hair": {"score": 8, "reason": "healthy and well-styled hair"},
    "overall": 8
  },
  "style_presentation": {
    "outfit": {"score": 8, "reason": "stylish and coordinated ensemble"},
    "grooming": {"score": 9, "reason": "polished and put-together appearance"},
    "posture": {"score": 8, "reason": "confident and erect posture"},
    "overall": 8
  },
  "final_notes": {
    "tier": "Attractive",
    "strengths": ["clear skin", "good bone structure", "expressive eyes"],
    "weaknesses": []
  }
}

Score must be 1-10 integer. Reason must be 2-4 words. Tier must be one of: Average, Above Average, Attractive, Highly Attractive, Elite, Exceptional. Provide ONLY valid JSON, no markdown or explanation."""

        # Call OpenRouter API
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://vscaletest.local',
            'X-Title': 'V-Scale Analyzer'
        }
        
        payload = {
            "model": "meta-llama/llama-3.2-11b-vision-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                        }
                    ]
                }
            ],
            "max_tokens": 2000
        }
        
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Parse JSON from response
            # Find JSON in response (might have some text before/after)
            try:
                # Try to extract JSON
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    # Get filename from filepath
                    filename = os.path.basename(filepath)
                    save_response(filename, {
                        'status': 'done',
                        'analysis': analysis,
                        'completed_at': datetime.now().isoformat()
                    })
                    update_pending_status(filename, 'analyzed')
                    
                    # Send completion notification
                    send_discord_notification(f"✅ Analysis complete for {filename}")
                    return True
            except json.JSONDecodeError:
                print(f"Failed to parse JSON from response: {content[:200]}")
        else:
            print(f"OpenRouter API error: {response.status_code} - {response.text[:200]}")
            
    except Exception as e:
        print(f"Analysis error: {str(e)}")
    
    return False

def start_background_analysis(filename, filepath):
    """Start analysis in background thread"""
    threading.Thread(target=analyze_with_llama_vision, args=(filepath, filename)).start()

@app.route('/')
def index():
    with open('index.html', 'r') as f:
        return f.read(), 200, {'Content-Type': 'text/html'}

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    
    if not data or 'image' not in data:
        return jsonify({'error': 'No image provided'}), 400
    
    # Save image
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'vs_{timestamp}.png'
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    # Decode base64
    image_data = data['image'].split(',')[1] if ',' in data['image'] else data['image']
    
    with open(filepath, 'wb') as f:
        f.write(base64.b64decode(image_data))
    
    # Add to pending queue
    add_pending(filename)
    
    # Send Discord notification
    notification_sent, notification_msg = send_discord_notification(filename)
    
    # Run AI analysis SYNCHRONOUSLY (waits for result - no background thread issues)
    print(f"Starting analysis for {filename}...")
    success = analyze_with_llama_vision(filepath)
    
    if success:
        return jsonify({
            'success': True,
            'filename': filename,
            'message': '✅ Analysis complete!'
        })
    else:
        return jsonify({
            'success': True,
            'filename': filename,
            'message': 'Image uploaded. Analysis may take a moment...'
        })

@app.route('/check/<filename>')
def check_response(filename):
    """Check if there's a response for this image"""
    response = get_response(filename)
    if response:
        return jsonify(response)
    return jsonify({'status': 'pending'})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/pending')
def list_pending():
    """List all pending analyses"""
    return jsonify(get_pending())

@app.route('/respond', methods=['POST'])
def respond():
    """Endpoint for manual analysis results (from Sinka)"""
    data = request.get_json()
    filename = data.get('filename')
    analysis = data.get('analysis')
    
    if not filename or not analysis:
        return jsonify({'error': 'Missing filename or analysis'}), 400
    
    save_response(filename, {
        'status': 'done',
        'analysis': analysis,
        'completed_at': datetime.now().isoformat()
    })
    
    update_pending_status(filename, 'analyzed')
    
    # Send completion notification to Discord
    send_discord_notification(f"✅ Analysis complete for {filename}")
    
    return jsonify({'success': True})

@app.route('/configure', methods=['POST'])
def configure_webhook():
    """Set Discord webhook URL"""
    global DISCORD_WEBHOOK_URL
    data = request.get_json()
    webhook_url = data.get('webhook_url', '')
    
    if webhook_url:
        DISCORD_WEBHOOK_URL = webhook_url
        return jsonify({'success': True, 'message': 'Discord webhook configured!'})
    return jsonify({'error': 'No webhook URL provided'}), 400

@app.route('/config')
def get_config():
    """Check if webhook is configured"""
    return jsonify({
        'webhook_configured': bool(DISCORD_WEBHOOK_URL),
        'auto_analysis': True
    })

@app.route('/test-analysis', methods=['POST'])
def test_analysis():
    """Test the AI analysis with a sample image"""
    data = request.get_json()
    image_data = data.get('image', '')
    
    if not image_data:
        return jsonify({'error': 'No image provided'}), 400
    
    # Save test image
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'test_{timestamp}.png'
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    # Decode base64
    img_data = image_data.split(',')[1] if ',' in image_data else image_data
    with open(filepath, 'wb') as f:
        f.write(base64.b64decode(img_data))
    
    # Start analysis
    start_background_analysis(filename, filepath)
    
    return jsonify({
        'success': True,
        'filename': filename,
        'message': 'Test analysis started!'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)