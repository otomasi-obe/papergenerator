"""Backend badge-tier configuration.

Centralized config for all badge-tier benefits.
Frontend mirrors this in src/config/badgeTiers.ts
"""
from typing import TypedDict


class BadgeTierConfig(TypedDict):
    label: str
    # Token quota
    token_quota_monthly: int
    # Image generation
    image_models: list[str]
    image_quality: str
    image_quota_monthly: int  # max images per month
    # Job limits
    max_parallel_jobs: int
    # Revision limits
    max_free_revisions: int  # -1 = unlimited
    # Journal access
    journal_access: str  # description
    # Other benefits
    benefits: list[str]


BADGE_TIERS: dict[str, BadgeTierConfig] = {
    "trial": {
        "label": "Trial",
        "token_quota_monthly": 500_000,
        "image_models": ["SDXL Lightning", "Dreamshaper (fallback)"],
        "image_quality": "Cepat, kualitas standar",
        "image_quota_monthly": 10,
        "max_parallel_jobs": 1,
        "max_free_revisions": 0,
        "journal_access": "10 jurnal (Trial tier)",
        "benefits": [
            "Coba fitur dasar",
            "1 job paralel",
            "Template standar",
        ],
    },
    "starter": {
        "label": "Starter",
        "token_quota_monthly": 1_000_000,
        "image_models": ["SDXL Lightning", "Flux 2 (fallback)"],
        "image_quality": "Cepat, kualitas baik",
        "image_quota_monthly": 30,
        "max_parallel_jobs": 1,
        "max_free_revisions": 1,
        "journal_access": "19 jurnal (Trial + Starter)",
        "benefits": [
            "Antrian normal",
            "Template standar",
            "1 revisi gratis",
            "1 job paralel",
        ],
    },
    "pro": {
        "label": "Pro",
        "token_quota_monthly": 3_000_000,
        "image_models": ["Flux 2", "Dreamshaper", "SDXL (fallback)"],
        "image_quality": "Excellent, model Flux 2 + Dreamshaper",
        "image_quota_monthly": 100,
        "max_parallel_jobs": 2,
        "max_free_revisions": 3,
        "journal_access": "36 jurnal (Trial + Starter + Pro)",
        "benefits": [
            "Prioritas tinggi",
            "Template premium (sebagian jurnal)",
            "3 revisi gratis",
            "2 job paralel",
            "Support email prioritas",
        ],
    },
    "elite": {
        "label": "Elite",
        "token_quota_monthly": 10_000_000,
        "image_models": ["GPT-Image (OpenAI)", "Flux 2 (fallback)"],
        "image_quality": "Best overall - GPT-Image + Flux 2 fallback",
        "image_quota_monthly": 500,
        "max_parallel_jobs": 3,
        "max_free_revisions": -1,  # unlimited
        "journal_access": "Semua 49 jurnal unlocked",
        "benefits": [
            "Prioritas tertinggi",
            "Revisi unlimited",
            "3 job paralel",
            "Semua template jurnal unlocked",
            "Akses humanizer",
            "Early access fitur beta",
            "+10% token bonus tiap pembelian",
            "Support chat prioritas",
        ],
    }
}


# Default tier for users without badge
DEFAULT_TIER = "trial"

# Tier rank: higher = more access (used for badge upgrade logic)
TIER_RANK: dict[str, int] = {"trial": 0, "starter": 1, "pro": 2, "elite": 3}

# Map payment amount (IDR) → badge tier
AMOUNT_TO_BADGE: dict[int, str] = {
    1000: "trial",      # Test 1k
    41000: "starter",   # Harian
    125000: "pro",      # Mingguan (Pro)
    315000: "elite",    # Bulanan (Elite)
}


def get_tier_config(badge: str | None) -> BadgeTierConfig:
    """Get tier config for a badge, fallback to trial."""
    if badge and badge in BADGE_TIERS:
        return BADGE_TIERS[badge]
    return BADGE_TIERS[DEFAULT_TIER]


def upgrade_user_badge(user, amount: int) -> str | None:
    """
    Upgrade user badge based on payment amount.
    Never downgrades. Returns new badge if changed, else None.
    """
    new_badge = AMOUNT_TO_BADGE.get(amount)
    if not new_badge:
        return None
    current_rank = TIER_RANK.get(user.badge or DEFAULT_TIER, 0)
    new_rank = TIER_RANK.get(new_badge, 0)
    if new_rank > current_rank:
        user.badge = new_badge
        user.badge_expires_at = None  # paid tier: no expiry until token runs out (ponytail: add expiry on tier downgrade)
        return new_badge
    return None


def get_token_quota(badge: str | None) -> int:
    """Get monthly token quota for badge."""
    return get_tier_config(badge)["token_quota_monthly"]


def get_image_quota(badge: str | None) -> int:
    """Get monthly image generation quota for badge."""
    return get_tier_config(badge)["image_quota_monthly"]


def get_max_parallel_jobs(badge: str | None) -> int:
    """Get max parallel jobs for badge."""
    return get_tier_config(badge)["max_parallel_jobs"]


def get_max_free_revisions(badge: str | None) -> int:
    """Get max free revisions for badge (-1 = unlimited)."""
    return get_tier_config(badge)["max_free_revisions"]


def get_image_models(badge: str | None) -> list[str]:
    """Get image model list for badge (for API)."""
    # Map to actual model IDs used in image_api_v2.py that work with OTOMASI proxy (ai.otomasi.app)
    # Only cx/gpt-5.5-image and cx/gpt-5.5 work reliably (others: Cloudflare 502, Alibaba 502, GPT-Image 401)
    badge = badge or DEFAULT_TIER
    # Working fallbacks for all tiers (only these 2 models work on OTOMASI proxy)
    working_fallbacks = ["cx/gpt-5.5-image", "cx/gpt-5.5"]
    # Kie.ai models (require KIE_AI_API_KEY env var)
    nano_models = ["nano-banana-2-lite", "nano-banana", "nano-banana-edit"]
    zimage_model = "z-image"
    cf_models = [
        "cf/@cf/black-forest-labs/flux-2-klein-9b",       # Flux 2 (free, quota-limited)
        "cf/@cf/bytedance/stable-diffusion-xl-lightning", # SDXL Lightning (free)
        "cf/@cf/lykon/dreamshaper-8-lcm",                 # Dreamshaper (free)
        "cf/@cf/stabilityai/stable-diffusion-xl-base-1.0",# SDXL Base (free)
    ]
    if badge == "elite":
        # GPT-5.5 primary + all Kie.ai + Cloudflare fallbacks
        return working_fallbacks + nano_models + [zimage_model] + cf_models
    elif badge == "pro":
        # Nano Banana primary + Z-Image + Cloudflare (no GPT-5.5, no Elite models)
        return nano_models + [zimage_model] + cf_models
    elif badge == "starter":
        # Z-Image primary + Cloudflare fallbacks
        return [zimage_model] + [
            "cf/@cf/bytedance/stable-diffusion-xl-lightning",
            "cf/@cf/black-forest-labs/flux-2-klein-9b",
            "cf/@cf/lykon/dreamshaper-8-lcm",
        ]
    elif badge == "trial":
        # Z-Image primary + Cloudflare fallbacks (limited)
        return [zimage_model] + [
            "cf/@cf/bytedance/stable-diffusion-xl-lightning",
            "cf/@cf/lykon/dreamshaper-8-lcm",
        ]
    return BADGE_TIERS[DEFAULT_TIER]["image_models"]


# Export for convenience
__all__ = [
    "BADGE_TIERS",
    "DEFAULT_TIER",
    "TIER_RANK",
    "AMOUNT_TO_BADGE",
    "get_tier_config",
    "upgrade_user_badge",
    "get_token_quota",
    "get_image_quota",
    "get_max_parallel_jobs",
    "get_max_free_revisions",
    "get_image_models",
]