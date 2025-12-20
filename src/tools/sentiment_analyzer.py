import logging
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers library not found. Sentiment analysis will use keyword fallback.")

class SentimentAnalyzer:
    """
    A component to analyze news sentiment for the Macro-Arbitrage strategy.
    Uses FinBERT (if available) and Alpaca News.
    """
    
    def __init__(self, data_handler=None):
        self.data_handler = data_handler
        self.nlp_pipeline = None
        
        if TRANSFORMERS_AVAILABLE:
            try:
                # Use FinBERT for financial sentiment
                logger.info("Loading FinBERT model... (this may take a moment)")
                self.nlp_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
                logger.info("FinBERT model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load FinBERT: {e}")
                self.nlp_pipeline = None

        # Keywords that suggest a sector-wide or macroeconomic driver
        self.systematic_keywords = [
            "Fed", "Federal Reserve", "Interest Rates", "Inflation", "CPI", "PPI",
            "Jobs Report", "Unemployment", "Treasury", "Yield", "Sector", "Industry",
            "Regulation", "Supply Chain", "Tariff", "Trade War", "OPEC", "Oil",
            "Energy", "Tech", "Banking", "Rotation", "Market-wide", "ETF", "Index"
        ]
        
        # Keywords that suggest an idiosyncratic (company-specific) driver
        self.idiosyncratic_keywords = [
            "Earnings", "Revenue", "Missed", "Beat", "Guidance", "CEO", "CFO",
            "Resign", "Fire", "Lawsuit", "Scandal", "Merger", "Acquisition",
            "Product Launch", "Recall", "Upgrade", "Downgrade", "Analyst", "Dividend"
        ]

    def analyze_news(self, symbol: str, lookback_hours: int = 24) -> dict:
        """
        Fetches news for a symbol and determines if the move is Systematic or Idiosyncratic.
        """
        if not self.data_handler:
            logger.warning("DataHandler not provided to SentimentAnalyzer.")
            return {"sentiment_score": 0, "driver_type": "neutral", "headline": "No DataHandler"}

        # Fetch news
        start_time = (datetime.now() - timedelta(hours=lookback_hours)).strftime('%Y-%m-%d')
        
        news_items = self.data_handler.get_news(symbol, start=start_time, limit=10)
        
        if not news_items:
             return {"sentiment_score": 0, "driver_type": "neutral", "headline": "No news found."}

        scores = []
        systematic_count = 0
        idiosyncratic_count = 0
        
        for item in news_items:
            headline = item.headline
            summary = item.summary if item.summary else ""
            text = f"{headline}. {summary}"
            
            # Keyword Check
            sys_score = sum(1 for k in self.systematic_keywords if k.lower() in text.lower())
            idio_score = sum(1 for k in self.idiosyncratic_keywords if k.lower() in text.lower())
            
            if sys_score > 0: systematic_count += 1
            if idio_score > 0: idiosyncratic_count += 1
                
            # NLP Score
            if self.nlp_pipeline:
                try:
                    # Truncate to 512 tokens approx (chars/4) to avoid errors, though pipeline handles some
                    result = self.nlp_pipeline(headline[:512])[0]
                    # FinBERT returns 'positive', 'negative', 'neutral'
                    score = result['score']
                    if result['label'] == 'negative':
                        score = -score
                    elif result['label'] == 'neutral':
                        score = 0
                    scores.append(score)
                except Exception as e:
                    logger.warning(f"NLP inference failed for headline: {e}")
        
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Determine Driver Type
        driver_type = "neutral"
        if systematic_count > idiosyncratic_count:
            driver_type = "systematic"
        elif idiosyncratic_count > systematic_count:
            driver_type = "idiosyncratic"
        elif systematic_count > 0: 
            driver_type = "systematic" 
            
        return {
            "sentiment_score": avg_score,
            "driver_type": driver_type,
            "headline": news_items[0].headline if news_items else ""
        }

    def validate_sector_move(self, leader_symbol: str, sector_keywords: list = None) -> bool:
        """
        Specific check for the Macro-Arbitrage strategy.
        Returns True if news suggests a Systematic/Sector move, False if Idiosyncratic.
        """
        # Look back only 4 hours for immediate news
        news_analysis = self.analyze_news(leader_symbol, lookback_hours=4)
        
        logger.info(f"[Sentiment] {leader_symbol}: Type={news_analysis['driver_type']}, Score={news_analysis['sentiment_score']:.2f}, Headline='{news_analysis['headline']}'")
        
        if news_analysis['driver_type'] == 'systematic':
            return True
        elif news_analysis['driver_type'] == 'idiosyncratic':
            return False
            
        return False
