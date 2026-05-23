"""
Frontend Logging Endpoint
==========================
Receives structured logs from frontend and stores them in backend logs.
"""
import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

log = logging.getLogger("papergenerator.frontend")

logging_bp = Blueprint('logging', __name__)


@logging_bp.route('/api/logs/frontend', methods=['POST'])
@jwt_required(optional=True)
def receive_frontend_logs():
    """
    Receive logs from frontend and write them to backend log files.
    
    Expected payload:
    {
        "logs": [
            {
                "ts": "2026-05-23T08:15:00.000Z",
                "level": "ERROR",
                "msg": "API call failed",
                "req_id": "1234-abcd",
                "url": "/papers",
                "method": "POST",
                "status": 500,
                ...
            }
        ]
    }
    """
    try:
        user_id = get_jwt_identity() if get_jwt_identity() else 'anonymous'
        data = request.get_json()
        
        if not data or 'logs' not in data:
            return jsonify({'error': 'Invalid payload'}), 400
        
        logs = data.get('logs', [])
        if not isinstance(logs, list):
            return jsonify({'error': 'logs must be an array'}), 400
        
        for entry in logs[:100]:
            if not isinstance(entry, dict):
                continue
            
            level = entry.get('level', 'INFO').upper()
            msg = entry.get('msg', 'Frontend log')
            
            extra = {
                'user_id': user_id,
                'source': 'frontend',
                'req_id': entry.get('req_id'),
                'frontend_url': entry.get('url'),
                'frontend_ts': entry.get('ts'),
            }
            
            for key in ['method', 'status', 'duration_ms', 'action', 'operation', 'error']:
                if key in entry:
                    extra[key] = entry[key]
            
            log_method = getattr(log, level.lower(), log.info)
            log_method(msg, extra=extra)
        
        return jsonify({'status': 'ok', 'received': len(logs)}), 200
        
    except Exception as e:
        log.exception("Failed to process frontend logs")
        return jsonify({'error': 'Internal server error'}), 500
