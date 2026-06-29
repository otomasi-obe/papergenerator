"""
Health Check API Blueprint
=====================================
System health monitoring endpoints for automation and monitoring.
"""

import os
import shutil
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from utils.database.models import db, safe_commit

health = Blueprint('health', __name__, url_prefix='/api/health')

_start_time = time.time()


@health.route('', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'service': 'papergenerator'
    }), 200


@health.route('/detailed', methods=['GET'])
def health_detailed():
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'service': 'papergenerator',
        'uptime_seconds': int(time.time() - _start_time),
        'checks': {}
    }

    db_healthy = check_database()
    health_data['checks']['database'] = db_healthy

    disk_info = check_disk_space()
    health_data['checks']['disk'] = disk_info

    memory_info = check_memory()
    health_data['checks']['memory'] = memory_info

    all_healthy = (
        db_healthy.get('status') == 'healthy' and
        disk_info.get('status') == 'healthy' and
        memory_info.get('status') == 'healthy'
    )

    if not all_healthy:
        health_data['status'] = 'degraded'

    status_code = 200 if all_healthy else 503
    return jsonify(health_data), status_code


def check_database():
    try:
        db.session.execute(db.text('SELECT 1'))
        safe_commit()
        return {
            'status': 'healthy',
            'message': 'Database connection OK'
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'message': f'Database connection failed: {str(e)}'
        }


def check_disk_space():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        usage = shutil.disk_usage(base_dir)

        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        percent_used = (usage.used / usage.total) * 100

        status = 'healthy' if free_gb > 1.0 else 'unhealthy'

        return {
            'status': status,
            'total_gb': round(total_gb, 2),
            'used_gb': round(used_gb, 2),
            'free_gb': round(free_gb, 2),
            'percent_used': round(percent_used, 2)
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Disk check failed: {str(e)}'
        }


def check_memory():
    try:
        import psutil
        mem = psutil.virtual_memory()

        status = 'healthy' if mem.percent < 90 else 'unhealthy'

        return {
            'status': status,
            'total_gb': round(mem.total / (1024**3), 2),
            'available_gb': round(mem.available / (1024**3), 2),
            'percent_used': round(mem.percent, 2)
        }
    except ImportError:
        return {
            'status': 'unknown',
            'message': 'psutil not available'
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Memory check failed: {str(e)}'
        }
