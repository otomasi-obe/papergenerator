"""
Test Configuration for Playwright MCP Tests
Centralized configuration for test execution parameters
"""

# Application URLs
APP_BASE_URL = "http://localhost:5173"
API_BASE_URL = "http://localhost:5000"

# Test User Credentials
TEST_USERS = {
    "beginner": {
        "username": "beginner_user",
        "password": "test123",
        "email": "beginner@test.com"
    },
    "intermediate": {
        "username": "intermediate_user",
        "password": "test123",
        "email": "intermediate@test.com"
    },
    "advanced": {
        "username": "advanced_user",
        "password": "test123",
        "email": "advanced@test.com"
    },
    "hybrid": {
        "username": "hybrid_user",
        "password": "test123",
        "email": "hybrid@test.com"
    },
    "default": {
        "username": "testuser",
        "password": "testpass",
        "email": "test@test.com"
    }
}

# Timeout Configuration (in seconds)
TIMEOUTS = {
    "page_load": 10,
    "login": 5,
    "navigation": 5,
    "ai_response": 30,
    "ai_response_long": 60,
    "literature_search": 60,
    "paper_generation": 300,  # 5 minutes
    "paper_generation_long": 600,  # 10 minutes for complex papers
    "element_wait": 10,
    "animation": 2
}

# Test Messages by User Level
TEST_MESSAGES = {
    "beginner": {
        "initial": "Saya bingung mau nulis paper tentang apa. Bisa bantu?",
        "follow_up_1": "Saya tertarik dengan AI dan machine learning",
        "follow_up_2": "Mungkin tentang deep learning untuk image recognition",
        "confirm": "Oke, tolong buatkan papernya"
    },
    "intermediate": {
        "initial": (
            "Saya ingin menulis paper tentang convolutional neural networks untuk "
            "klasifikasi gambar medis. Saya sudah punya dataset X-ray dan ingin "
            "membandingkan beberapa arsitektur CNN."
        ),
        "follow_up_1": (
            "Saya akan membandingkan ResNet, VGG, dan Inception. Dataset saya "
            "punya 10,000 gambar X-ray dengan 5 kategori penyakit."
        ),
        "follow_up_2": (
            "Saya akan menggunakan accuracy, precision, recall, dan F1-score. "
            "Tolong buatkan struktur papernya."
        )
    },
    "advanced": {
        "initial": """Saya ingin menulis paper dengan detail berikut:

Judul: "Deep Learning-Based Medical Image Classification Using Ensemble CNN Architectures"

Abstract: Penelitian ini mengusulkan metode ensemble dari tiga arsitektur CNN 
(ResNet-50, VGG-16, Inception-v3) untuk klasifikasi gambar X-ray paru-paru. 
Dataset terdiri dari 10,000 gambar dengan 5 kategori: Normal, Pneumonia, 
COVID-19, Tuberculosis, dan Lung Cancer.

Metodologi:
- Preprocessing: resize 224x224, normalisasi, augmentasi data
- Training: 80% train, 10% validation, 10% test
- Optimizer: Adam dengan learning rate 0.001
- Epochs: 100 dengan early stopping
- Ensemble: weighted voting dari 3 model

Hasil:
- Accuracy: 94.5%
- Precision: 93.8%
- Recall: 94.2%
- F1-Score: 94.0%
- ResNet-50 memberikan performa terbaik individual (92.3%)

Kesimpulan: Ensemble method meningkatkan akurasi 2.2% dibanding single model.

Tolong generate paper lengkap dengan struktur IEEE format."""
    },
    "hybrid": {
        "initial": (
            "Saya sudah upload beberapa paper tentang CNN untuk medical imaging. "
            "Tolong carikan paper-paper terkait lainnya yang relevan, terutama "
            "yang membahas ensemble methods dan X-ray classification."
        ),
        "follow_up": (
            "Bagus! Sekarang tolong buatkan systematic literature review "
            "berdasarkan paper yang saya upload dan yang kamu temukan."
        )
    }
}

# Expected AI Response Keywords by User Level
EXPECTED_KEYWORDS = {
    "beginner": {
        "initial_response": ["bidang", "topik", "minat", "tertarik", "apa"],
        "follow_up_1": ["spesifik", "aplikasi", "masalah", "fokus", "detail"],
        "follow_up_2": ["judul", "struktur", "outline", "bagian", "saran"]
    },
    "intermediate": {
        "initial_response": ["arsitektur", "metodologi", "dataset", "detail", "jelaskan"],
        "follow_up_1": ["evaluasi", "metrik", "hasil", "performa", "ukur"]
    },
    "advanced": {
        "initial_response": ["lengkap", "generate", "membuat", "siap", "mulai"]
    },
    "hybrid": {
        "initial_response": ["mencari", "paper", "literatur", "cari", "temukan"],
        "follow_up": ["menemukan", "hasil", "paper", "relevan", "ditemukan"]
    }
}

# Element Selectors (CSS/XPath)
SELECTORS = {
    "login": {
        "username_field": "input[type='text'], input[name='username']",
        "password_field": "input[type='password'], input[name='password']",
        "submit_button": "button[type='submit'], button:contains('Login')"
    },
    "dashboard": {
        "new_paper_button": "button:contains('New Paper'), button:contains('Buat Paper')",
        "paper_list": ".paper-list, [data-testid='paper-list']"
    },
    "editor": {
        "chat_input": "textarea, input[type='text'].chat-input",
        "send_button": "button:contains('Send'), button:contains('Kirim')",
        "chat_messages": ".chat-message, [data-testid='chat-message']",
        "generation_status": ".generation-status, [data-testid='generation-status']",
        "paper_content": ".paper-content, [data-testid='paper-content']"
    },
    "literature": {
        "upload_button": "button:contains('Upload'), input[type='file']",
        "file_list": ".file-list, [data-testid='file-list']"
    }
}

# Verification Criteria
VERIFICATION = {
    "paper_structure": {
        "required_sections": ["title", "abstract", "introduction", "methodology", "results", "conclusion"],
        "min_sections": 3,
        "min_content_length": 100  # characters per section
    },
    "ai_response": {
        "min_length": 20,  # characters
        "max_wait_time": 30,  # seconds
        "retry_attempts": 3
    },
    "generation": {
        "progress_indicators": ["generating", "processing", "creating"],
        "completion_indicators": ["complete", "done", "finished", "selesai"],
        "error_indicators": ["error", "failed", "gagal"]
    }
}

# Test Data Files
TEST_FILES = {
    "literature": {
        "bibtex": "backend/tests/fixtures/sample_literature.bib",
        "pdf": "backend/tests/fixtures/sample_paper.pdf",
        "csv": "backend/tests/fixtures/sample_references.csv"
    }
}

# Retry Configuration
RETRY = {
    "max_attempts": 3,
    "delay": 2,  # seconds between retries
    "backoff_multiplier": 2  # exponential backoff
}

# Logging Configuration
LOGGING = {
    "level": "INFO",
    "format": "[%(asctime)s] [%(levelname)s] %(message)s",
    "file": "backend/tests/logs/playwright_tests.log",
    "console": True
}

# Screenshot Configuration
SCREENSHOTS = {
    "enabled": True,
    "on_failure": True,
    "on_success": False,
    "directory": "backend/tests/screenshots",
    "format": "png"
}

# Performance Thresholds
PERFORMANCE = {
    "page_load_max": 5,  # seconds
    "ai_response_max": 30,  # seconds
    "generation_max": 300,  # seconds
    "api_response_max": 5  # seconds
}

# Feature Flags
FEATURES = {
    "enable_screenshots": True,
    "enable_video_recording": False,
    "enable_trace": False,
    "enable_network_logging": True,
    "enable_console_logging": True,
    "parallel_execution": False,
    "headless": True
}

# Environment-specific Configuration
ENVIRONMENTS = {
    "local": {
        "app_url": "http://localhost:5173",
        "api_url": "http://localhost:5000"
    },
    "staging": {
        "app_url": "https://staging.papergenerator.com",
        "api_url": "https://api-staging.papergenerator.com"
    },
    "production": {
        "app_url": "https://papergenerator.com",
        "api_url": "https://api.papergenerator.com"
    }
}

# Current Environment
CURRENT_ENV = "local"

def get_config(env=None):
    """Get configuration for specified environment."""
    env = env or CURRENT_ENV
    return ENVIRONMENTS.get(env, ENVIRONMENTS["local"])

def get_timeout(operation):
    """Get timeout for specific operation."""
    return TIMEOUTS.get(operation, 30)

def get_test_user(user_type="default"):
    """Get test user credentials."""
    return TEST_USERS.get(user_type, TEST_USERS["default"])

def get_test_message(user_level, message_type="initial"):
    """Get test message for user level."""
    return TEST_MESSAGES.get(user_level, {}).get(message_type, "")

def get_expected_keywords(user_level, response_type="initial_response"):
    """Get expected keywords for verification."""
    return EXPECTED_KEYWORDS.get(user_level, {}).get(response_type, [])
