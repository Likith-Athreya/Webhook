from flask import Flask, request, jsonify, render_template_string
from pymongo import MongoClient
from datetime import datetime
import json
import os
from dotenv import load_dotenv

app = Flask(__name__)

# MongoDB connection
load_dotenv()
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client['github_webhooks']
collection = db['events']

def format_timestamp(timestamp_str):
    """Convert GitHub timestamp to required format"""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%d %B %Y - %I:%M %p UTC')
    except:
        return timestamp_str

def process_push_event(payload):
    """Process push webhook event"""
    return {
        'id': payload.get('after', ''),
        'author': payload.get('pusher', {}).get('name', 'Unknown'),
        'to_branch': payload.get('ref', '').replace('refs/heads/', ''),
        'timestamp': format_timestamp(payload.get('head_commit', {}).get('timestamp', '')),
        'action': 'push',
        'message': f"{payload.get('pusher', {}).get('name', 'Unknown')} pushed to {payload.get('ref', '').replace('refs/heads/', '')} on {format_timestamp(payload.get('head_commit', {}).get('timestamp', ''))}"
    }

def process_pull_request_event(payload):
    """Process pull request webhook event"""
    pr = payload.get('pull_request', {})
    return {
        'id': str(pr.get('id', '')),
        'author': pr.get('user', {}).get('login', 'Unknown'),
        'from_branch': pr.get('head', {}).get('ref', ''),
        'to_branch': pr.get('base', {}).get('ref', ''),
        'timestamp': format_timestamp(pr.get('created_at', '')),
        'action': 'pull_request',
        'message': f"{pr.get('user', {}).get('login', 'Unknown')} submitted a pull request from {pr.get('head', {}).get('ref', '')} to {pr.get('base', {}).get('ref', '')} on {format_timestamp(pr.get('created_at', ''))}"
    }

def process_merge_event(payload):
    """Process merge webhook event (pull request merged)"""
    pr = payload.get('pull_request', {})
    return {
        'id': str(pr.get('id', '')),
        'author': pr.get('merged_by', {}).get('login', 'Unknown'),
        'from_branch': pr.get('head', {}).get('ref', ''),
        'to_branch': pr.get('base', {}).get('ref', ''),
        'timestamp': format_timestamp(pr.get('merged_at', '')),
        'action': 'merge',
        'message': f"{pr.get('merged_by', {}).get('login', 'Unknown')} merged branch {pr.get('head', {}).get('ref', '')} to {pr.get('base', {}).get('ref', '')} on {format_timestamp(pr.get('merged_at', ''))}"
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """GitHub webhook endpoint"""
    try:
        payload = request.json
        event_type = request.headers.get('X-GitHub-Event')
        
        event_data = None
        
        if event_type == 'push':
            event_data = process_push_event(payload)
        elif event_type == 'pull_request':
            action = payload.get('action')
            if action == 'opened':
                event_data = process_pull_request_event(payload)
            elif action == 'closed' and payload.get('pull_request', {}).get('merged'):
                event_data = process_merge_event(payload)
        
        if event_data:
            # Add metadata
            event_data['created_at'] = datetime.utcnow()
            event_data['raw_payload'] = payload
            
            # Store in MongoDB
            collection.insert_one(event_data)
            
            return jsonify({'status': 'success', 'message': 'Event processed'}), 200
        
        return jsonify({'status': 'ignored', 'message': 'Event type not processed'}), 200
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/events')
def get_events():
    """API endpoint to get latest events"""
    try:
        events = list(collection.find(
            {}, 
            {'_id': 0, 'raw_payload': 0}  # Exclude _id and raw_payload from response
        ).sort('created_at', -1).limit(20))
        
        return jsonify(events)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    """Main UI page"""
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GitHub Webhook Monitor</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f6f8fa;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .events-container {
                background: white;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            .event-item {
                padding: 15px 20px;
                border-bottom: 1px solid #e1e4e8;
                display: flex;
                align-items: center;
            }
            .event-item:last-child {
                border-bottom: none;
            }
            .event-icon {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                margin-right: 15px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                color: white;
            }
            .push { background-color: #28a745; }
            .pull_request { background-color: #0366d6; }
            .merge { background-color: #6f42c1; }
            .event-content {
                flex: 1;
            }
            .event-message {
                margin: 0;
                font-size: 14px;
                color: #24292e;
            }
            .loading {
                text-align: center;
                padding: 40px;
                color: #586069;
            }
            .no-events {
                text-align: center;
                padding: 40px;
                color: #586069;
            }
            .status {
                position: fixed;
                top: 10px;
                right: 10px;
                padding: 5px 10px;
                background: #28a745;
                color: white;
                border-radius: 4px;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="status" id="status">●</div>
        
        <div class="header">
            <h1>GitHub Webhook Monitor</h1>
            <p>Real-time monitoring of repository events</p>
        </div>
        
        <div class="events-container">
            <div id="events-list" class="loading">
                Loading events...
            </div>
        </div>

        <script>
            let isPolling = true;
            
            function updateStatus(connected) {
                const status = document.getElementById('status');
                status.textContent = connected ? '●' : '○';
                status.style.backgroundColor = connected ? '#28a745' : '#dc3545';
            }
            
            function getEventIcon(action) {
                const icons = {
                    'push': 'P',
                    'pull_request': 'PR',
                    'merge': 'M'
                };
                return icons[action] || '?';
            }
            
            async function fetchEvents() {
                try {
                    const response = await fetch('/api/events');
                    const events = await response.json();
                    
                    updateStatus(true);
                    
                    const eventsList = document.getElementById('events-list');
                    
                    if (events.length === 0) {
                        eventsList.innerHTML = '<div class="no-events">No events yet. Make some changes to your repository!</div>';
                        return;
                    }
                    
                    eventsList.innerHTML = events.map(event => `
                        <div class="event-item">
                            <div class="event-icon ${event.action}">
                                ${getEventIcon(event.action)}
                            </div>
                            <div class="event-content">
                                <p class="event-message">${event.message}</p>
                            </div>
                        </div>
                    `).join('');
                    
                } catch (error) {
                    console.error('Error fetching events:', error);
                    updateStatus(false);
                }
            }
            
            // Initial load
            fetchEvents();
            
            // Poll every 15 seconds
            setInterval(fetchEvents, 15000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)