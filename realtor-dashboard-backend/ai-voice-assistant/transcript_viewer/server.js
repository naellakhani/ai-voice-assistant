const WebSocket = require('ws');
const express = require('express');
const http = require('http');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Serve the HTML file from current directory
app.use(express.static(__dirname));

// Store connected clients
const clients = new Set();

wss.on('connection', function(ws) {
    console.log('Client connected - Total clients:', clients.size + 1);
    clients.add(ws);
    
    ws.on('close', function() {
        console.log('Client disconnected - Total clients:', clients.size - 1);
        clients.delete(ws);
    });
});

// Broadcast to all clients
function broadcast(data) {
    console.log('Broadcasting to', clients.size, 'clients:', data);
    clients.forEach(function(client) {
        if (client.readyState === WebSocket.OPEN) {
            try {
                client.send(JSON.stringify(data));
                console.log('Sent to client successfully');
            } catch (error) {
                console.error('Failed to send to client:', error);
                clients.delete(client);
            }
        }
    });
}

// HTTP endpoint to receive transcript from Python
app.use(express.json());
app.post('/transcript', function(req, res) {
    console.log('=== RECEIVED POST REQUEST ===');
    console.log('Request body:', req.body);
    
    var speaker = req.body.speaker;
    var text = req.body.text;
    
    if (!speaker || !text) {
        console.error('Missing speaker or text in request');
        return res.status(400).json({ error: 'Missing speaker or text' });
    }
    
    console.log('Broadcasting: ' + speaker + ': ' + text);
    broadcast({ speaker: speaker, text: text });
    res.json({ success: true });
});

app.post('/call-summary', function(req, res) {
    console.log('=== RECEIVED CALL SUMMARY ===');
    console.log('Extracted data:', req.body);
    
    // Send special message type for call summary
    broadcast({ 
        type: 'call_summary', 
        data: req.body 
    });
    res.json({ success: true });
});

// Add a test endpoint
app.post('/test', function(req, res) {
    console.log('Test endpoint hit');
    broadcast({ speaker: 'ai', text: 'Test message from server' });
    res.json({ success: true, message: 'Test message sent' });
});

var PORT = 3001;
server.listen(PORT, function() {
    console.log('Server running on http://localhost:' + PORT);
    console.log('WebSocket clients will connect to ws://localhost:' + PORT);
    console.log('POST to /transcript to send messages');
    console.log('POST to /test for testing');
});