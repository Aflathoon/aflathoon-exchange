"""
Live price ticker + news endpoints. Public read-only.
"""
from flask import Blueprint, jsonify
from app.services.crypto_prices import get_prices
from app.services.crypto_news import get_news

ticker_bp = Blueprint('ticker', __name__)


@ticker_bp.route('/api/prices')
def prices():
    """Live crypto prices + 24h change."""
    return jsonify(get_prices().snapshot())


@ticker_bp.route('/api/news')
def news():
    """Curated news + trending + global market data."""
    return jsonify(get_news().snapshot())
